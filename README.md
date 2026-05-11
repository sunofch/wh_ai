# wh_graphrag_re - All-in-VLM 多模态AI港口指令解析系统

基于 Python 的多模态AI系统，集成了语音识别、视觉语言模型、结构化解析、RAG知识检索和AGV仓储调度，专门用于港口/海事领域的智能化作业。

## 项目特色

- **All-in-VLM架构**：单一VLM模型处理多模态输入+RAG增强
- **vLLM高性能推理**：PagedAttention优化，推理速度提升30-50%
- **双模式RAG**：传统向量检索 + GraphRAG知识图谱
- **AGV仓储调度**：四层调度架构（WMS→WES→Fleet→Simulation），含聚类、TSP、Regret-2全局优化
- **REST API服务**：FastAPI事件驱动调度接口，支持VLM解析→库存预留→AGV入队全链路
- **多模态输入**：音频、文本、图像统一处理
- **结构化输出**：Pydantic模型确保输出质量

---

## 系统一：港口指令解析

### 多模态输入支持
- **音频输入**：支持实时录音（5秒）和音频文件（WAV、MP3、M4A、FLAC、OGG）
- **文本输入**：直接输入文本指令或文本文件
- **图像输入**：支持图片分析（JPG、PNG、BMP、WebP）

### 智能解析引擎
- **ASR语音识别**：基于OpenAI Whisper large-v3-turbo，支持中文
- **VLM视觉理解**：支持Qwen2-VL和Qwen3.5-VL两种模型，可动态切换
- **vLLM高性能推理**：使用vLLM引擎，PagedAttention优化推理速度
- **结构化输出**：解析为标准化的港口指令格式（Pydantic模型）

### RAG知识增强
- **传统RAG**：基于BGE-M3向量和BM25混合检索
- **GraphRAG**：知识图谱关系推理，支持多跳检索
- **重排序**：使用BGE-reranker-v2-m3优化结果

### 数据流

```
输入 (Audio/Text/Image)
  → ASR (Whisper) → Text
  → RAG 检索上下文 (Traditional 或 Graph 模式)
  → VLM (Qwen2-VL / Qwen3.5-VL + vLLM) → 结构化 JSON
  → Parser (Pydantic 验证) → PortInstruction
```

---

## 系统二：AGV 智能仓储调度

基于四层调度架构的AGV仓储仿真系统，支持双向batch优化（OUTBOUND多取一送 + INBOUND一取多送）。

### 架构

```
WMS层：订单生成、库存管理（SQLite WAL双表）、任务分解
  ↓
WES层：方向感知聚类（精确batch键分组）
  ↓
Fleet层：Regret-2全局分配 → 簇间TSP排序 → 逐簇TSP排序 → 路径规划
  ↓
Simulation层：AGV仿真执行、充电调度、指标统计
```

### 调度流程

```
随机/VLM工单 → 任务分解(TransportTask)
  → 聚类(按精确dest/pick分组 → 空间合并 → 容量拆分)
  → Regret-2分配(簇→AGV, 最小化makespan)
  → 簇间TSP排序(OR-Tools)
  → 逐簇TSP排序(OR-Tools, 双向batch)
  → A*路径规划(方向感知)
  → 仿真执行(自动检测batch + 充电管理)
```

### 核心优化模块

| 模块 | 算法 | 说明 |
|------|------|------|
| M1 路径缓存 | BFS预计算 | 预计算所有关键节点对的最短路径 |
| M2 聚类 | 精确batch键 + Ward层次聚类 | 按dest/pick精确分组，空间合并相近组 |
| M3 TSP | OR-Tools TSP | 簇间排序 + 簇内双向batch排序 |
| M4 Regret-2 | Makespan-aware Regret-2 | 全局簇→AGV分配，三元组评分键最小化makespan |

### 消融实验结果

10组随机种子（42, 123, 456, 789, 2024, 3141, 6666, 9999, 12345, 54321）均值：

| 实验 | makespan | 距离 | 边际提升 |
|------|----------|------|---------|
| Baseline (无优化) | 1933 | 8616 | - |
| M1+M2 (+聚类) | 1033 | 3790 | 46.5% |
| M1+M2+M3 (+TSP) | 643 | 1849 | 37.8% |
| M1+M2+M3+M4 (+Regret-2) | 590 | 1700 | 8.2% |
| **总改善** | **-69.5%** | **-80.3%** | |

### 地图配置

57×47网格仓库地图：
- 3×3=9个行列式货架区域（14×10储位）
- 6个端口（3入3出）
- 主通道3格宽 + 巷道1格单向
- 8台AGV + 4个充电桩

### 运行方式

```bash
# 纯仿真
python main_simulation.py

# 指定地图和订单数
python main_simulation.py medium_57x47 40

# 带动画
python main_simulation.py --animate medium_57x47_cluster 40

# 消融实验（4级对比）
python main_simulation.py --ablation
```

### 仓库模块结构

```
src/warehouse/
  models.py              - Pydantic v2 数据模型
  maps/
    base.py              - 地图注册基类
    medium_57x47.py      - 57×47 仓库地图定义
    medium_57x47_cluster.py - 同布局，AGV起点聚集（负载均衡压力测试）
  wms/
    config.py            - 全局配置（Pydantic Settings）
    inventory.py         - 内存库存管理（轻量版）
    inventory_db.py      - SQLite持久化库存（WAL模式，双表，三阶段reserve/confirm/release）
    order_manager.py     - 工单生成（随机/VLM）
  wes/
    task_decomposer.py   - 任务分解
    clustering.py        - 精确batch键聚类
  fleet/
    map_builder.py       - 仓库地图构建（区域、端口、通道）
    pathfinding.py       - A*路径规划（方向感知+缓存）
    tsp.py               - OR-Tools TSP（双向batch）
    allocator.py         - Makespan-aware Regret-2分配 + 贪心降级
    charging.py          - 充电调度
    fleet_manager.py     - Fleet层总编排
  simulation/
    agv.py               - AGV仿真模型
    simulator.py         - 仿真执行引擎
    metrics.py           - 指标统计
```

---

## 系统三：REST API 服务

FastAPI服务，提供从港口指令解析到AGV调度的完整链路。

### 数据流

```
POST /instructions (文本/音频/图像)
  → VLM/规则解析 → PortInstruction
  → 库存查询 + reserve(预留)
  → 工单入队 (OrderQueue)
  → 调度触发 (事件驱动: 满10条 OR 30秒超时 OR URGENT)
  → run_pipeline (TaskDecomposer → Clusterer → Fleet → Simulator)
  → 成功 confirm / 失败 release 库存预留
  → 结果存储 (GET /result/{run_id})
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/instructions` | 提交港口指令，返回instruction_id和解析结果 |
| `GET` | `/status` | 查看队列状态和调度状态 |
| `GET` | `/result/{run_id}` | 获取调度结果（makespan、距离、利用率等） |
| `GET` | `/result/{run_id}/animation` | 按需生成并下载调度动画GIF |

### 启动 API 服务

```bash
python main_api.py             # 默认 0.0.0.0:8000
python main_api.py --port 9000  # 自定义端口
```

### API 调用示例

#### 1. 文本指令（最常用）

```bash
curl -X POST http://localhost:8000/instructions \
  -H "Content-Type: application/json" \
  -d '{"text": "需要2个弹性爪型联轴器，型号为GS-28-98A-LOVEJOY"}'
```

```json
{
  "instruction_id": "a3f1c2d4-...",
  "status": "queued",
  "vlm_available": true,
  "parsed": {
    "part_name": "抗磨液压油",
    "quantity": 2,
    "model": "L-HM46-200L-KUNLUN",
    "action_required": "出库",
    "is_urgent": false,
    "description": null
  },
  "resolved_location": "Cons1_R1_B2",
  "resolved_en_name": "Anti-Wear Hydraulic Oil",
  "target_port": "OUT_1"
}
```

#### 2. 音频文件指令

```bash
# 将音频文件编码为 base64 后提交
AUDIO_B64=$(base64 -w0 /path/to/audio.wav)

curl -X POST http://localhost:8000/instructions \
  -H "Content-Type: application/json" \
  -d "{\"audio_base64\": \"$AUDIO_B64\"}"
```

```python
import base64, requests

with open("audio.wav", "rb") as f:
    audio_b64 = base64.b64encode(f.read()).decode()

resp = requests.post("http://localhost:8000/instructions",
                     json={"audio_base64": audio_b64})
print(resp.json())
```

#### 3. 图像指令

```python
import base64, requests

with open("image.jpg", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()

resp = requests.post("http://localhost:8000/instructions",
                     json={"image_base64": image_b64})
print(resp.json())
```

#### 4. 查询队列和调度状态

```bash
curl http://localhost:8000/status
```

```json
{
  "queue_size": 3,
  "last_run_id": "b7e2a1f3-...",
  "last_run_at": "2026-05-11T17:30:00.123456",
  "scheduler_status": "idle"
}
```

`scheduler_status` 取值：`"idle"`（空闲）、`"failed"`（上次调度失败）。

#### 5. 获取调度结果

调度在满足触发条件（≥10条 / 30秒超时 / URGENT工单）后自动执行，结果通过 `last_run_id` 或 `instruction_id` 查询：

```bash
curl http://localhost:8000/result/b7e2a1f3-...
```

```json
{
  "run_id": "b7e2a1f3-...",
  "order_count": 10,
  "makespan": 612,
  "total_distance": 1843,
  "agv_utilization": 0.784,
  "planning_time": 2.31,
  "instructions": [
    "需要2桶抗磨液压油出库",
    "入库3个深沟球轴承",
    "..."
  ],
  "has_animation": true
}
```

#### 6. 下载调度动画

```bash
curl -o animation.gif \
  http://localhost:8000/result/b7e2a1f3-.../animation
```

```python
resp = requests.get("http://localhost:8000/result/b7e2a1f3-.../animation")
with open("animation.gif", "wb") as f:
    f.write(resp.content)
```

#### 7. 错误响应

| HTTP 状态码 | `error` 字段 | 含义 |
|-------------|-------------|------|
| 400 | `parse_failed` | 无有效输入或解析结果为空 |
| 409 | `insufficient_stock` | 库存不足，含 `requested` 和 `available` 字段 |
| 422 | `invalid_base64` | base64 解码失败，含 `field` 字段 |
| 404 | — | run_id 不存在或动画未生成 |

```bash
# 库存不足示例
curl -X POST http://localhost:8000/instructions \
  -H "Content-Type: application/json" \
  -d '{"text": "需要100个深沟球轴承"}'
```

```json
{
  "detail": {
    "error": "insufficient_stock",
    "part_name": "深沟球轴承",
    "requested": 100,
    "available": 5
  }
}
```

#### 8. Python 完整调用流程

```python
import time
import requests

BASE = "http://localhost:8000"

# 批量提交指令
instructions = [
    "需要2桶抗磨液压油出库",
    "入库3个深沟球轴承",
    "紧急出库1台三相异步电动机",
]
ids = []
for text in instructions:
    r = requests.post(f"{BASE}/instructions", json={"text": text})
    r.raise_for_status()
    ids.append(r.json()["instruction_id"])
    print(f"已入队: {r.json()['parsed']['part_name']} → {r.json()['target_port']}")

# 等待调度完成
while True:
    status = requests.get(f"{BASE}/status").json()
    print(f"队列: {status['queue_size']} 条, 调度: {status['scheduler_status']}")
    if status["queue_size"] == 0 and status["last_run_id"]:
        run_id = status["last_run_id"]
        break
    time.sleep(5)

# 获取结果
result = requests.get(f"{BASE}/result/{run_id}").json()
print(f"makespan={result['makespan']} 步, "
      f"距离={result['total_distance']}, "
      f"利用率={result['agv_utilization']:.1%}")

# 下载动画
gif = requests.get(f"{BASE}/result/{run_id}/animation")
with open("schedule.gif", "wb") as f:
    f.write(gif.content)
print("动画已保存为 schedule.gif")
```

#### 9. 多品类批量调度（10 条真实数据，可直接运行）

以下零件名称和型号均来自 `inventory_db.py` 的库存目录（`_PARTS_CATALOG`），10 条指令提交后自动触发批量调度（`SIZE_THRESHOLD=10`）。

**Python 一键运行脚本：**

```python
import time
import requests

BASE = "http://localhost:8000"

# 10 条指令覆盖 5 个品类（机械/电气/耗材/安全/工具）
instructions = [
    "出库2个深沟球轴承，型号6208-2RS-C3-SKF",
    "出库1台三相异步电动机，型号Y160M-4-11kW-ABB",
    "出库1桶抗磨液压油，型号L-HM46-200L-KUNLUN",
    "出库1个ABS工程安全帽，型号VGard-E2-WHT-MSA",
    "出库1把液压力矩扳手，型号HTW-3400Nm-ENERPAC",
    "出库1个弹性爪型联轴器，型号ROTEX-48-98ShA-KTR",
    "出库1台变频调速器，型号ACS580-039A-ABB",
    "出库1个高压液压油滤芯，型号HF-250x20Q-HYDAC",
    "出库1副防冲击护目镜，型号VMaxx-OTG-CLR-UVEX",
    "出库1台数字钳形万用表，型号F325-600V-FLUKE",
]

print("=== 提交 10 条指令 ===")
for text in instructions:
    r = requests.post(f"{BASE}/instructions", json={"text": text})
    r.raise_for_status()
    d = r.json()
    print(f"[{d['parsed']['part_name']}]  位置={d['resolved_location']}  端口={d['target_port']}")

print("\n=== 等待调度完成 ===")
while True:
    status = requests.get(f"{BASE}/status").json()
    print(f"  队列: {status['queue_size']} 条 | 调度状态: {status['scheduler_status']}")
    if status["queue_size"] == 0 and status["last_run_id"]:
        run_id = status["last_run_id"]
        break
    time.sleep(3)

print("\n=== 调度结果 ===")
result = requests.get(f"{BASE}/result/{run_id}").json()
print(f"  run_id       : {result['run_id']}")
print(f"  工单数        : {result['order_count']}")
print(f"  makespan     : {result['makespan']} 步")
print(f"  总移动距离    : {result['total_distance']}")
print(f"  AGV 利用率   : {result['agv_utilization']:.1%}")
print(f"  规划耗时      : {result['planning_time']:.2f}s")

print("\n=== 下载动画 ===")
gif = requests.get(f"{BASE}/result/{run_id}/animation")
with open("schedule.gif", "wb") as f:
    f.write(gif.content)
print("  动画已保存 → schedule.gif")
```

**等效的 curl 命令（逐条提交）：**

```bash
BASE=http://localhost:8000

curl -s -X POST $BASE/instructions -H "Content-Type: application/json" \
  -d '{"text": "出库2个深沟球轴承，型号6208-2RS-C3-SKF"}'

curl -s -X POST $BASE/instructions -H "Content-Type: application/json" \
  -d '{"text": "出库1台三相异步电动机，型号Y160M-4-11kW-ABB"}'

curl -s -X POST $BASE/instructions -H "Content-Type: application/json" \
  -d '{"text": "出库1桶抗磨液压油，型号L-HM46-200L-KUNLUN"}'

curl -s -X POST $BASE/instructions -H "Content-Type: application/json" \
  -d '{"text": "出库1个ABS工程安全帽，型号VGard-E2-WHT-MSA"}'

curl -s -X POST $BASE/instructions -H "Content-Type: application/json" \
  -d '{"text": "出库1把液压力矩扳手，型号HTW-3400Nm-ENERPAC"}'

curl -s -X POST $BASE/instructions -H "Content-Type: application/json" \
  -d '{"text": "出库1个弹性爪型联轴器，型号ROTEX-48-98ShA-KTR"}'

curl -s -X POST $BASE/instructions -H "Content-Type: application/json" \
  -d '{"text": "出库1台变频调速器，型号ACS580-039A-ABB"}'

curl -s -X POST $BASE/instructions -H "Content-Type: application/json" \
  -d '{"text": "出库1个高压液压油滤芯，型号HF-250x20Q-HYDAC"}'

curl -s -X POST $BASE/instructions -H "Content-Type: application/json" \
  -d '{"text": "出库1副防冲击护目镜，型号VMaxx-OTG-CLR-UVEX"}'

curl -s -X POST $BASE/instructions -H "Content-Type: application/json" \
  -d '{"text": "出库1台数字钳形万用表，型号F325-600V-FLUKE"}'

# 等调度完成后查结果（用 /status 中的 last_run_id）
curl -s $BASE/status
curl -s $BASE/result/<run_id>
curl -o schedule.gif $BASE/result/<run_id>/animation
```

> **说明**：上述零件名称与型号均来自 `inventory_db.py` 的 `_PARTS_CATALOG`，每条指令请求数量≤2，低于数据库初始库存（seeded 5～20），提交后必然命中库存。API 服务使用规则解析（VLM 未启动时降级），通过零件名 LIKE 匹配定位储位后执行 `reserve`，10 条触发批量调度。

### API 模块结构

```
src/api/
  app.py           - FastAPI工厂函数（依赖注入，便于测试）
  models.py        - 请求/响应Pydantic模型
  queue_manager.py - 事件驱动工单队列（asyncio.Event，含urgent优先队列和重试）
  scheduler.py     - 后台调度协程（事件驱动批量触发，成功confirm/失败release）
```

---

## 快速开始

### 1. 环境要求

- Python 3.10+
- PyTorch 2.10+（支持CUDA 12.8）
- FFmpeg（音频处理）
- 可选：sounddevice（实时录音）

### 2. 安装依赖

```bash
git clone https://github.com/sunofch/wh_ai.git
cd wh_ai

# 安装核心依赖
pip install -r requirements.txt

# 安装PyTorch（推荐CUDA 12.8）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

# 安装FFmpeg（Linux）
sudo apt-get install ffmpeg
```

### 3. 环境配置

```bash
cp .env.example .env
# 编辑 .env 配置 API Key 等
```

### 4. 运行

```bash
# 港口指令解析（需先启动vLLM服务器）
python start_vlm_server.py        # 终端1：启动服务器
python main_interaction.py         # 终端2：交互式解析

# AGV仓储调度（无需GPU，纯CPU即可）
python main_simulation.py --ablation

# REST API服务（可选：不启动vLLM则降级为规则解析）
python main_api.py
```

---

## 港口指令解析详细说明

### vLLM 服务器管理

vLLM 服务器需独立启动，多个程序可共享使用：

```bash
python start_vlm_server.py     # 启动（根据 VLM_MODEL_TYPE 自动选择模型）
python status_vlm_server.py    # 查看状态
# 停止：kill $(cat /tmp/vlm_server.pid) 或 Ctrl+C
```

**模型对比**：
- **Qwen2-VL-2B**（~5GB）：推理速度快，适合资源受限环境
- **Qwen3.5-4B**（~9GB）：平衡性能和速度

通过 `VLM_MODEL_TYPE=qwen2` 或 `qwen35` 切换。

### 交互式使用

```bash
python main_interaction.py
```

- 输入文本指令：`需要更换3号传送带的电机`
- 拖入图片/音频文件
- 实时录音：输入 `r`（5秒）
- RAG管理：`rag:status` / `rag:enable` / `rag:disable` / `rag:rebuild`

### 输出格式

```json
{
  "part_name": "传送带电机",
  "quantity": 5,
  "model": "YVF2-132S-4",
  "installation_equipment": "3号传送带",
  "location": "港区B区",
  "description": "需要更换电机",
  "action_required": "更换"
}
```

### API使用示例

```python
from src.asr import get_asr_instance
from src.vlm import get_vlm_instance
from src.parser import PortInstructionParser

asr = get_asr_instance()
vlm = get_vlm_instance()
parser = PortInstructionParser()

audio_text = asr.transcribe("audio.wav")
result = vlm.extract_structured_info(text=audio_text, enable_rag=True)
instruction = parser.parse_output(vlm_result=result, raw_text=audio_text)
```

---

## 配置说明

### 港口指令解析配置（.env）

```ini
# ASR
ASR_MODEL=large-v3-turbo
ASR_LANGUAGE=zh

# VLM
VLM_MODEL_TYPE=qwen2              # qwen2 或 qwen35

# RAG
RAG_ENABLED=true
RAG_GRAPH_ENABLED=true
RAG_EMBEDD_MODEL=BAAI/bge-m3
GRAPH_RAG_DEEPSEEK_API_KEY=xxx     # GraphRAG 所需
```

### AGV调度配置（src/warehouse/wms/config.py）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `AGV_MOVE_TIME` | 1 | 移动一格时间 |
| `AGV_LOAD_UNLOAD_TIME` | 8 | 装卸时间 |
| `AGV_LOW_BATTERY_THRESHOLD` | 20 | 低电量阈值 |
| `AGV_CHARGE_TIME` | 20 | 充满电时间 |
| `ORDER_NUM` | 40 | 订单数量 |
| `TSP_TIME_LIMIT` | 1 | TSP求解时限(秒) |
| `RANDOM_SEED` | 42 | 随机种子 |

消融开关（`AblationFlags`）：
- `enable_path_cache`：M1 路径缓存
- `enable_clustering`：M2 聚类
- `enable_tsp`：M3 TSP排序
- `enable_regret`：M4 Regret-2全局分配

### API调度配置（src/api/queue_manager.py）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `WINDOW_SECONDS` | 30 | 批次超时窗口（秒） |
| `SIZE_THRESHOLD` | 10 | 批次大小触发阈值 |
| `MAX_RETRIES` | 1 | 失败批次最大重试次数 |

---

## 项目结构

```
wh_graphrag_re/
├── main_interaction.py       # 港口指令解析入口（交互式）
├── main_simulation.py        # AGV调度仿真入口
├── main_api.py               # REST API服务启动入口
├── main_rag.py               # RAG测试CLI
├── start_vlm_server.py       # vLLM服务器启动
├── status_vlm_server.py      # vLLM服务器状态查询
├── src/
│   ├── api/                  # REST API模块
│   │   ├── app.py            # FastAPI工厂函数
│   │   ├── models.py         # 请求/响应模型
│   │   ├── queue_manager.py  # 事件驱动工单队列
│   │   └── scheduler.py      # 后台调度协程
│   ├── asr/whisper.py        # Whisper ASR
│   ├── vlm/                  # VLM模块（router + qwen2 + qwen35 + server）
│   ├── parser/parser.py      # PortInstruction解析器
│   ├── rag/                  # RAG模块（manager + traditional + graph）
│   ├── common/               # 配置、Reranker、工具函数
│   └── warehouse/            # AGV调度系统（见上方模块结构）
├── data/
│   ├── knowledge_base/       # 港口设备知识库
│   ├── vector_db/            # 向量数据库（运行时生成）
│   └── graph_db/             # 图谱数据库（运行时生成）
├── tests/                    # 测试套件
├── .env.example              # 环境变量模板
└── requirements.txt          # 依赖列表
```

---

## 故障排查

| 问题 | 解决方案 |
|------|---------|
| 模型加载失败 | 检查网络和磁盘空间（BGE-M3: ~2.3GB, Qwen2-VL: ~5GB） |
| RAG检索失败 | 确认 `data/knowledge_base/` 有文档，运行 `rag:rebuild` |
| GBK编码错误 | `python -X utf8 main_interaction.py` |
| GPU内存不足 | 降低 `VLLM_SERVER_GPU_MEM_UTIL` 或使用 Qwen2-VL-2B |
| API库存不足 | 检查 `data/inventory.db` 或重启API服务重建库存 |
| API调度无响应 | 检查队列是否满足触发条件（≥10条或等待30秒） |

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件
