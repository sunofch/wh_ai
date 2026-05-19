# wh_graphrag_re 高并发重构方案

> 日期：2026-05-18
> 背景：课题四考核指标要求 2028 年验收时支持 ≥ 1000 TPS、系统可用性 ≥ 99.9%、响应时间 < 2 秒。
> 当前状态：模拟仿真阶段原型，实际吞吐约 5-20 TPS。

---

## 一、考核指标 vs 当前能力

| 指标 | 目标值（2028验收） | 当前能力 | 差距 |
|------|-----------------|---------|------|
| 高并发支持 | ≥ 1000 TPS | ~5-20 TPS | 差 50-200 倍 |
| 系统可用性 | ≥ 99.9% | 单进程无 HA | 不满足 |
| 响应时间 | < 2 秒 | LLM 推理 2-10 秒 | 勉强/不满足 |
| 横向扩展 | 支持 | 内存队列+单进程 | 不支持 |

**重要前提**：当前代码是研究原型（2026 年模拟仿真阶段），所有算法核心（Agent、GraphRAG、AGV 四层调度）已验证正确。2027-2028 年系统集成阶段替换基础设施即可，**算法代码一行不动**。

---

## 二、四大瓶颈分析

### 瓶颈 1：LLM 推理（最致命）

**位置**：`src/api/app.py:115`

```python
# 现在：每条请求同步等 LLM，2-10 秒/条
order = await asyncio.to_thread(st.parser.parse, text=req.text, ...)
```

- 单条 ReAct Agent 推理（多轮工具调用）：2~10 秒
- 单台 vLLM 服务器（Qwen3.5-4B）实际吞吐：5~20 TPS
- 结论：LLM 这一跳单独就把 1000 TPS 打到了 5-20 TPS

### 瓶颈 2：SQLite 写并发上限

**位置**：`src/warehouse/wms/inventory_db.py`

- SQLite WAL 模式写并发上限约几十 TPS
- 每次 `reserve()` 写操作串行化，1000 TPS 下锁竞争导致延迟膨胀到秒级

### 瓶颈 3：内存队列单点

**位置**：`src/api/queue_manager.py`

- Python 内存 `deque`，进程重启队列清空，未处理工单丢失
- 不能水平扩展，两台机器各有各的队列

### 瓶颈 4：单 uvicorn 进程无 HA

**位置**：`main_api.py:91`

- `uvicorn.run(app, ...)` 单进程，任何崩溃服务即中断
- 99.9% 可用性 = 全年停机 < 8.7 小时，单进程做不到

---

## 三、重构方案

### P0：LLM 推理 — 三级快慢路径分离

核心思想：越快的路越早拦截，LLM 只处理真正歧义的请求。

```
来一条请求
  ├─ Level 1: Redis 缓存命中？  → 直接返回（<1ms）
  ├─ Level 2: 规则解析高置信？  → 规则路径（<10ms，已有 _rule_based_parse）
  └─ Level 3: 走 Agent LLM    → 异步后台（2~10s，不阻塞 HTTP）
```

**改法**（只改 `app.py`，其余不动）：

```python
async def post_instruction(req, request):
    # Level 1: Redis 缓存
    cache_key = hashlib.md5(req.text.encode()).hexdigest()
    cached = await redis.get(f"parse:{cache_key}")
    if cached:
        order = WorkOrder.model_validate_json(cached)
        return _build_response(order, from_cache=True)

    # Level 2: 规则解析（型号+数量+动作都能匹配时直接用）
    rule_result = rule_parser._rule_based_parse(req.text)
    if _is_high_confidence(rule_result):
        order = _to_work_order(rule_result)
        await redis.setex(f"parse:{cache_key}", 3600, order.model_dump_json())
        return _build_response(order)

    # Level 3: 入队等 LLM 异步处理，立即返回 pending
    instruction_id = str(uuid4())
    await redis.set(f"status:{instruction_id}", "pending", ex=300)
    await task_queue.enqueue("llm_parse_task", req.text, instruction_id)
    return JSONResponse({"instruction_id": instruction_id, "status": "pending"})
```

**vLLM 多实例**（通过 LiteLLM 代理统一入口）：

```yaml
# litellm_config.yaml
model_list:
  - model_name: qwen35
    litellm_params:
      model: openai/qwen3.5
      api_base: http://gpu-server-1:8001/v1
  - model_name: qwen35
    litellm_params:
      model: openai/qwen3.5
      api_base: http://gpu-server-2:8001/v1
router_settings:
  routing_strategy: least-busy
```

```python
# agent.py 改一行，算法逻辑完全不变
llm = ChatOpenAI(base_url="http://litellm-proxy:4000/v1", model="qwen35")
```

---

### P0：内存队列 → Redis Streams

**只改 `queue_manager.py`，`scheduler_loop` 改几行，`run_pipeline` 一行不动。**

```python
# src/api/queue_manager.py 替换实现
import redis.asyncio as aioredis

STREAM_KEY = "wh:orders"
GROUP_NAME  = "scheduler"

class RedisOrderQueue:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = aioredis.from_url(redis_url)

    async def push(self, order: WorkOrder) -> None:
        await self.redis.xadd(STREAM_KEY, {
            "data":     order.model_dump_json(),
            "priority": order.priority.value,
        })

    async def drain(self, batch_size: int = 10) -> list[WorkOrder]:
        entries = await self.redis.xreadgroup(
            GROUP_NAME, "consumer-1", {STREAM_KEY: ">"}, count=batch_size
        )
        if not entries:
            return []
        orders = []
        for _, msgs in entries:
            for msg_id, data in msgs:
                orders.append(WorkOrder.model_validate_json(data[b"data"]))
                await self.redis.xack(STREAM_KEY, GROUP_NAME, msg_id)
        return orders

    async def size(self) -> int:
        return await self.redis.xlen(STREAM_KEY)
```

优势：持久化（重启不丢）、分布式（多实例共享）、天然支持消费者组。

---

### P1：SQLite → PostgreSQL 异步

**只替换 `inventory_db.py` 底层连接，三阶段事务逻辑（reserve/confirm/release）完全保留。**

```python
# src/warehouse/wms/inventory_db.py 改造
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/wh_db",
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession)

class StockManager:
    async def reserve(self, model: str, qty: int, order_id: str) -> str | None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                # SELECT FOR UPDATE 行级锁，防止并发超卖（SQLite 没有此功能）
                row = await session.execute(
                    select(Inventory)
                    .where(Inventory.model == model)
                    .with_for_update()
                )
                item = row.scalar_one_or_none()
                if item is None or item.available < qty:
                    return None
                item.reserved += qty
                return item.location
```

PostgreSQL `SELECT FOR UPDATE` 行级锁支持数千 TPS 并发写入。

---

### P1：单进程 → Gunicorn 多 Worker

**零代码改动，只改启动命令。**

```bash
# 替换 python main_api.py
gunicorn main_api:build_app() \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --preload
```

4 个 worker 各跑一个事件循环，`run_pipeline` 并行度翻 4 倍。
状态必须在 Redis/PostgreSQL 里（换掉内存队列和 SQLite 后自然满足）。

---

### P2：LiteLLM 多 vLLM 实例

见 P0 LLM 部分，只需配置 `litellm_config.yaml` 和修改 `agent.py` 的 `base_url`。

---

### P3：nginx 负载均衡多机（99.9% HA）

```nginx
upstream wh_api {
    least_conn;
    server 192.168.1.10:8000;
    server 192.168.1.11:8000;
    server 192.168.1.12:8000;
    keepalive 32;
}
server {
    listen 80;
    location / {
        proxy_pass http://wh_api;
        proxy_read_timeout 30s;
    }
}
```

三台机器任意一台宕机服务不中断，满足 99.9% 可用性。

---

## 四、改动范围汇总

| 优先级 | 改动项 | 改哪个文件 | 算法代码受影响 | 难度 |
|--------|--------|-----------|--------------|------|
| 🔴 P0 | 三级解析分流 + Redis 缓存 | `app.py` | 否 | 低 |
| 🔴 P0 | 内存队列 → Redis Streams | `queue_manager.py`，`scheduler_loop` 改几行 | 否 | 中 |
| 🟠 P1 | SQLite → PostgreSQL async | `inventory_db.py` 底层连接层 | 否 | 中 |
| 🟠 P1 | 单进程 → Gunicorn 多 Worker | 启动命令 | 否 | 低 |
| 🟡 P2 | LiteLLM 多 vLLM 实例 | `agent.py` 改 base_url 一行 | 否 | 低 |
| 🟢 P3 | nginx 多机部署 | 运维配置 | 否 | 低 |

**核心结论**：`FleetManager`、`Simulator`、`TaskDecomposer`、`OrderClusterer`、`PathFinder`、`TSPSolver`、`TaskAllocator` 等 AGV 调度算法，以及 ReAct Agent、GraphRAG，全部**一行不动**。所有重构在队列/数据库/HTTP 层，与算法层通过 Pydantic 数据模型完全解耦。

---

## 五、参考 GitHub 项目

### arq — 异步 Redis 任务队列（替换内存队列的核心参考）

> https://github.com/samuelcolvin/arq ⭐ ~2.5k

P0 内存队列替换方案的直接参考来源。arq 是专为 Python asyncio 设计的轻量任务队列，底层基于 Redis，与 FastAPI 配合是生产环境替换 `asyncio.Queue` 的标准选型。比 Celery 轻量，原生 async/await，无需额外 broker 配置。

本项目借鉴点：
- Redis Streams 消费者组模式（`xadd` / `xreadgroup` / `xack`）
- 任务持久化与重试机制（对应现有 `OrderQueue.requeue()`）
- Worker 与 FastAPI 同进程或独立部署均可

```python
# arq 典型用法（供参考，本项目采用 Redis Streams 原生 API 实现更贴合批调度语义）
async def run_llm_parse(ctx, text: str, instruction_id: str):
    order = await parse_with_agent(text)
    await redis.set(f"result:{instruction_id}", order.model_dump_json())

class WorkerSettings:
    functions = [run_llm_parse]
    redis_settings = RedisSettings(host="localhost", port=6379)
```

---

### LiteLLM — 统一 LLM 网关 / 多实例负载均衡

> https://github.com/BerriAI/litellm ⭐ ~45k

P0/P2 vLLM 多实例负载均衡的参考来源。LiteLLM 提供 OpenAI 兼容的统一代理接口，支持将请求分发到多个 vLLM 实例，内置 `least-busy`、`latency-based`、`usage-based` 等路由策略，无需修改业务代码（`ChatOpenAI` 只改 `base_url`）。

本项目借鉴点：
- 多 vLLM 实例的 `least-busy` 路由（对应 `agent.py` 的 LLM 初始化）
- 统一 fallback：主实例超时自动切备用实例
- 内置请求级 token 计费与限流（后期可用于成本控制）

```yaml
# litellm_config.yaml（直接可用）
model_list:
  - model_name: qwen35
    litellm_params:
      model: openai/qwen3.5
      api_base: http://gpu-server-1:8001/v1
      api_key: EMPTY
  - model_name: qwen35
    litellm_params:
      model: openai/qwen3.5
      api_base: http://gpu-server-2:8001/v1
      api_key: EMPTY
router_settings:
  routing_strategy: least-busy
  num_retries: 2
  timeout: 30
```

---

### asyncpg — 高性能 PostgreSQL 异步驱动

> https://github.com/MagicStack/asyncpg ⭐ ~7k

P1 SQLite → PostgreSQL 改造的底层驱动。asyncpg 是 PostgreSQL 最快的 Python 异步客户端，基于 asyncio 原生实现（非线程池包装），连接池吞吐比 psycopg2 线程模式高 3~5 倍。

本项目借鉴点：
- 配合 SQLAlchemy 2.0 async engine 使用（`postgresql+asyncpg://`）
- 连接池配置（`pool_size=20, max_overflow=40`）
- `SELECT FOR UPDATE` 行级锁替代 SQLite 全表锁

---

### SQLAlchemy 2.0 异步引擎

> https://github.com/sqlalchemy/sqlalchemy ⭐ ~10k

P1 的 ORM 层参考。SQLAlchemy 2.0 引入原生 async engine，配合 asyncpg 是 FastAPI 生产环境数据库访问的标准模式（FastAPI 官方文档推荐）。

本项目借鉴点：
- `AsyncSession` + `sessionmaker` 替代同步 `sqlite3.connect()`
- `async with session.begin()` 事务块（对应现有三阶段事务 reserve/confirm/release）
- 声明式 ORM 模型替代现有手写 SQL

---

### 架构参考：FastAPI 官方 full-stack 模板

> https://github.com/fastapi/full-stack-fastapi-template ⭐ ~30k

高并发 FastAPI 生产架构的权威参考。该模板展示了 FastAPI + PostgreSQL + Redis + Celery + nginx 的完整生产化组合，与本项目重构方向完全对应。

本项目借鉴的架构模式：
- 依赖注入管理数据库连接（对应现有 `create_app` 工厂函数）
- 后台任务与 HTTP 服务解耦（对应 `scheduler_loop` 改为独立 worker）
- nginx 反向代理 + Gunicorn 多 worker 部署配置

---

## 六、实施节点建议

| 时间 | 阶段 | 重构内容 |
|------|------|---------|
| 2026（当前） | 模拟仿真 | 不做生产化改造，专注算法验证 |
| 2027 上半年 | 系统集成 | P0：Redis Streams + 三级解析分流 |
| 2027 下半年 | 联调测试 | P1：PostgreSQL + Gunicorn 多 Worker |
| 2028 上半年 | 现场部署 | P2/P3：LiteLLM 多实例 + nginx 多机 |
| 2028 下半年 | 验收 | 第三方压测，目标 ≥ 1000 TPS |
