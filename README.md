# wh_graphrag_re

多模态港口指令解析、知识检索与 AGV 仓储调度一体化实验项目。项目把自然语言/图像/音频指令解析为结构化 `WorkOrder`，再通过 WMS/WES/Fleet/Simulation 四层调度链路完成批量 AGV 路径规划与仿真。

核心能力：

- 多模态输入：文本、图片 base64、音频 base64/文件，音频由 Whisper 转写。
- Agent 指令解析：基于 LangGraph/LangChain 的 ReAct Agent 与 Supervisor 多智能体流水线。
- 知识增强：传统 RAG（BGE-M3 + BM25 + reranker）与 GraphRAG（LlamaIndex PropertyGraphIndex + Neo4j）。
- 库存工单：SQLite 库存、库存预留/确认/释放、缺货补货单生成。
- AGV 调度：精确 batch 键聚类、A* 路径规划、OR-Tools TSP、Regret-2 分配、充电调度与指标统计。
- API 服务：FastAPI + Redis/Celery，可在 vLLM 在线时异步跑 Agent，离线时降级为规则解析。

## 目录

- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [运行入口](#运行入口)
- [REST API](#rest-api)
- [RAG 与 Neo4j](#rag-与-neo4j)
- [AGV 调度](#agv-调度)
- [配置](#配置)
- [测试](#测试)
- [项目结构](#项目结构)
- [故障排查](#故障排查)

## 系统架构

### 端到端链路

```text
文本 / 图片 / 音频
  -> ASR / VLM / 规则解析
  -> instruction_agent 解析语义
  -> inventory_agent 查询库存并创建 WorkOrder
  -> Redis / 内存队列聚合批次
  -> agv_agent 调用确定性调度算法
  -> TaskDecomposer -> Clusterer -> FleetManager -> Simulator
  -> 调度指标 / GIF 动画 / 库存确认或释放
```

### 多智能体分工

| 模块 | 文件 | 职责 |
| --- | --- | --- |
| Supervisor | `src/agents/supervisor.py` | 编排指令解析与库存工单创建 |
| Instruction Agent | `src/agents/instruction_agent.py` | LLM 语义解析，可查询知识库 |
| Inventory Agent | `src/agents/inventory_agent.py` | 查询库存并生成 `WorkOrder` |
| AGV Agent | `src/agents/agv_agent.py` | 纯算法批量调度，不依赖 LLM |
| 单 Agent 兼容入口 | `src/agent/agent.py` | `main_interaction.py` 使用的 ReAct Agent |

LLM 只参与语义理解、信息补全和工单创建；AGV 分配、路径规划和仿真由确定性算法完成。

## 快速开始

### 1. 环境要求

- Python 3.10+
- FFmpeg（音频处理）
- Redis（API 异步 Agent/Celery 模式需要；不可用时 API 会降级为内存队列）
- Neo4j 5.x + APOC（GraphRAG 需要）
- CUDA GPU（运行 vLLM、Whisper 大模型、embedding/reranker 时推荐）

### 2. 安装

```bash
cd /home/catlab/wh/wh_graphrag_re

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

如需手动安装 PyTorch，请按本机 CUDA 版本选择对应 wheel。例如 CUDA 12.8：

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

Linux 安装 FFmpeg：

```bash
sudo apt-get install ffmpeg
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

至少检查这些项：

```ini
# vLLM / VLM
VLM_MODEL_TYPE=qwen35
VLM35_MODEL=Qwen/Qwen3.5-4B
VLLM_SERVER_BASE_PORT=8000
VLLM_OFFLINE=true

# Redis / Celery
REDIS_URL=redis://localhost:6379/0
REDIS_RESULT_URL=redis://localhost:6379/1
SCHEDULER_WINDOW_SECONDS=30
SCHEDULER_SIZE_THRESHOLD=10

# GraphRAG / Neo4j
RAG_ENABLED=true
RAG_GRAPH_ENABLED=true
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password
GRAPH_RAG_DEEPSEEK_API_KEY=your-api-key
```

### 4. 最小可运行命令

不依赖 GPU、不依赖 vLLM 的 AGV 仿真：

```bash
python main_simulation.py
python main_simulation.py --animate medium_57x47 40
python main_simulation.py --ablation
```

API 规则解析降级模式：

```bash
python main_api.py
curl -X POST http://localhost:8000/instructions \
  -H "Content-Type: application/json" \
  -d '{"text":"出库2个深沟球轴承，型号6208-2RS-C3-SKF"}'
```

完整 Agent 模式需要先启动 Redis、vLLM 和 Celery Worker：

```bash
redis-server
VLM_MODEL_TYPE=qwen35 python start_vlm_server.py
python main_worker.py
python main_api.py
```

## 运行入口

| 命令 | 用途 |
| --- | --- |
| `python main_simulation.py [map] [order_num]` | 纯 AGV 仿真 |
| `python main_simulation.py --animate medium_57x47 40` | 仿真并输出 `output/animation.gif` |
| `python main_simulation.py --ablation [map] [order_num]` | 消融实验 |
| `python main_agv.py` | 菜单式 AGV 演示入口 |
| `python main_interaction.py` | 多模态 ReAct Agent 交互式解析 |
| `python main_rag.py` | 传统 RAG / GraphRAG CLI |
| `python start_vlm_server.py` | 启动 vLLM OpenAI 兼容服务 |
| `python status_vlm_server.py` | 检查 vLLM 服务状态 |
| `python main_api.py --host 0.0.0.0 --port 8000` | 启动 FastAPI 服务 |
| `python main_worker.py --concurrency 2 --queues urgent,default` | 启动 Celery Worker |
| `python restock_inventory.py --qty 100` | 补充 SQLite 库存 |
| `python test_api_batch.py --animation` | 批量提交 10 条指令并下载调度动画 |

## REST API

服务入口：`main_api.py`，默认监听 `0.0.0.0:8000`。

### 工作模式

- `vlm_available=true`：API 把请求交给 Celery，Worker 调用 Supervisor/Agent 生成 `WorkOrder`，写入 Redis 队列。
- `vlm_available=false`：API 使用 `PortInstructionParser` 规则解析降级，同步创建 `WorkOrder` 并入队。
- 调度触发条件：紧急订单、普通队列数量达到 `SCHEDULER_SIZE_THRESHOLD`，或等待超过 `SCHEDULER_WINDOW_SECONDS`。

### 端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/instructions` | 提交文本/音频/图像指令 |
| `GET` | `/agent-result/{instruction_id}` | 查询 Celery Agent 处理结果 |
| `GET` | `/status` | 查询队列、最近批次和调度状态 |
| `GET` | `/result/{run_id}` | 查询批次调度结果 |
| `GET` | `/result/{run_id}/animation` | 按需生成并下载 GIF 动画 |

### 请求示例

文本指令：

```bash
curl -X POST http://localhost:8000/instructions \
  -H "Content-Type: application/json" \
  -d '{"text":"紧急出库1台三相异步电动机，型号Y160M-4-11kW-ABB"}'
```

响应示例：

```json
{
  "instruction_id": "a3f1c2d4-...",
  "status": "queued",
  "vlm_available": false,
  "parsed": {
    "part_name": "三相异步电动机",
    "quantity": 1,
    "model": "Y160M-4-11kW-ABB",
    "action_required": null,
    "is_urgent": false,
    "description": null
  }
}
```

图片或音频指令使用 base64 字段：

```python
import base64
import requests

with open("image.jpg", "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode()

resp = requests.post(
    "http://localhost:8000/instructions",
    json={"text": "识别图片中的备件并出库", "image_base64": image_base64},
)
print(resp.json())
```

查询批次结果：

```bash
curl http://localhost:8000/status
curl http://localhost:8000/result/<run_id>
curl -o schedule.gif http://localhost:8000/result/<run_id>/animation
```

`/result/{run_id}` 返回：

```json
{
  "run_id": "b7e2a1f3-...",
  "order_count": 10,
  "makespan": 612,
  "total_distance": 1843,
  "agv_utilization": 0.784,
  "planning_time": 2.31,
  "instructions": ["..."],
  "has_animation": true
}
```

## RAG 与 Neo4j

项目支持两套检索：

- 传统 RAG：`src/rag/traditional.py`，基于知识库 markdown、BGE-M3 embedding、BM25、RRF 融合和 BGE reranker。
- GraphRAG：`src/rag/graph.py`，基于 LlamaIndex `PropertyGraphIndex` 与 Neo4j 持久化图谱，支持 vector/synonym 子检索器和实体关系展开。

知识库目录：

```text
data/knowledge_base/
  01_mechanical_parts.md
  02_electrical_parts.md
  03_consumable_parts.md
  04_safety_equipment.md
  05_tools.md
```

启动 Neo4j 后运行：

```bash
python main_rag.py
```

常用命令：

```text
status / stats    查看状态
rebuild           重建索引或图谱
quit              退出
```

Neo4j 安装、APOC 配置和图谱清理见 [NEO4J.md](NEO4J.md) 与 [docs/neo4j_setup.md](docs/neo4j_setup.md)。

## AGV 调度

### 四层架构

```text
WMS: 订单生成、库存管理、任务分解
  -> WES: 精确 batch 键聚类、空间合并、容量拆分
  -> Fleet: Regret-2 分配、簇间/簇内 TSP、A* 路径规划、充电策略
  -> Simulation: AGV 执行仿真、冲突处理、指标统计
```

### 关键优化

| 模块 | 实现 | 说明 |
| --- | --- | --- |
| M1 路径缓存 | `src/warehouse/fleet/pathfinding.py` | 预计算关键点对最短路 |
| M2 聚类 | `src/warehouse/wes/clustering.py` | 按出入库方向与目标端口分组 |
| M3 TSP | `src/warehouse/fleet/tsp.py` | OR-Tools 优化簇间/簇内访问顺序 |
| M4 分配 | `src/warehouse/fleet/allocator.py` | Makespan-aware Regret-2 全局分配 |

### 地图

当前注册地图：

- `medium_57x47`：57x47 仓库地图，9 个货架区域、6 个端口、8 台 AGV、4 个充电桩。
- `medium_57x47_cluster`：同布局但 AGV 初始位置聚集，用于负载均衡压力测试。

地图相关文件位于 `src/warehouse/maps/`，可视化工具在 `src/warehouse/visualize_map.py` 和 `src/warehouse/visualize_animation.py`。

## 配置

### 应用配置

`src/common/config.py` 从项目根目录 `.env` 读取配置，覆盖 ASR、VLM、RAG、GraphRAG、Neo4j、Redis、vLLM 等模块。

### 仓库调度配置

`src/warehouse/wms/config.py` 使用 `WH_` 前缀环境变量覆盖：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `WH_MAP_NAME` | `medium_57x47` | 默认地图 |
| `WH_ORDER_NUM` | `40` | 默认随机订单数 |
| `WH_RANDOM_SEED` | `100` | 随机种子 |
| `WH_AGV_MAX_TASK_CAPACITY` | `20` | 单 AGV 任务容量 |
| `WH_TSP_TIME_LIMIT` | `1` | TSP 求解时限，单位秒 |
| `WH_A_MAX_SEARCH` | `50000` | A* 最大搜索步数 |

示例：

```bash
WH_ORDER_NUM=80 WH_RANDOM_SEED=42 python main_simulation.py
```

## 测试

运行全部测试：

```bash
pytest
```

只跑不依赖 vLLM 的冒烟链路：

```bash
pytest tests/test_smoke.py
```

API 批量端到端脚本：

```bash
python test_api_batch.py
python test_api_batch.py --animation
```

## 项目结构

```text
.
├── main_api.py                 # FastAPI 启动入口
├── main_worker.py              # Celery Worker 启动入口
├── main_interaction.py         # 多模态 ReAct Agent 交互入口
├── main_agv.py                 # 菜单式 AGV 演示入口
├── main_simulation.py          # AGV 仿真/消融入口
├── main_rag.py                 # RAG / GraphRAG CLI
├── start_vlm_server.py         # vLLM 服务启动脚本
├── status_vlm_server.py        # vLLM 状态脚本
├── restock_inventory.py        # 库存补充工具
├── config/prompts.yaml         # Agent / VLM 提示词
├── data/knowledge_base/        # markdown 知识库
├── docs/                       # 架构、Neo4j、API、项目文档
├── tests/                      # pytest 测试
└── src/
    ├── agent/                  # 单 ReAct Agent 与工具
    ├── agents/                 # Supervisor 多智能体
    ├── api/                    # FastAPI、Celery、队列、调度循环
    ├── asr/                    # Whisper ASR
    ├── common/                 # 配置、prompt、reranker、工具函数
    ├── parser/                 # PortInstruction 与规则解析
    ├── rag/                    # Traditional RAG 与 GraphRAG
    ├── vlm/                    # Qwen/VLM 路由与服务管理
    └── warehouse/              # WMS/WES/Fleet/Simulation 调度系统
```

## 故障排查

| 问题 | 处理 |
| --- | --- |
| vLLM 端口占用 | 检查 `VLLM_SERVER_BASE_PORT`，Qwen3.5 使用 `base_port + 1` |
| Agent 工具调用失败 | 确认 `VLM_MODEL_TYPE=qwen35`，并用 `start_vlm_server.py` 启动带 tool-call parser 的 vLLM |
| API 一直不调度 | 检查队列是否达到阈值、是否超过窗口，或提交包含“紧急”的订单 |
| Redis 不可用 | API 会降级到内存队列；完整异步 Agent 模式必须启动 Redis |
| Celery 无结果 | 检查 `main_worker.py` 是否运行，`REDIS_URL` 与 `REDIS_RESULT_URL` 是否一致 |
| Neo4j 连接失败 | 检查服务、账号密码、APOC 插件和 `.env` 的 `NEO4J_*` |
| GraphRAG 图谱为空 | 在 `main_rag.py` 中执行 `rebuild`，或清空 Neo4j 后重建 |
| 模型离线加载失败 | 检查本地 HuggingFace 缓存；`.env` 中 `VLLM_OFFLINE=true` 会禁止联网下载 |
| API 库存不足 | 运行 `python restock_inventory.py --qty 100`，或删除/重建本地库存数据库 |
| 编码问题 | 使用 `python -X utf8 ...` |

## 相关文档

- [docs/e2e_architecture.md](docs/e2e_architecture.md)
- [docs/api_usage.md](docs/api_usage.md)
- [docs/multiagent_architecture.md](docs/multiagent_architecture.md)
- [docs/neo4j_setup.md](docs/neo4j_setup.md)
- [src/warehouse/README.md](src/warehouse/README.md)
