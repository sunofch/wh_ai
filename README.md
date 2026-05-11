# wh_graphrag_re - All-in-VLM 多模态AI港口指令解析系统

基于 Python 的多模态AI系统，集成了语音识别、视觉语言模型、结构化解析、RAG知识检索和AGV仓储调度，专门用于港口/海事领域的智能化作业。

## 项目特色

- **All-in-VLM架构**：单一VLM模型处理多模态输入+RAG增强
- **vLLM高性能推理**：PagedAttention优化，推理速度提升30-50%
- **双模式RAG**：传统向量检索 + GraphRAG知识图谱
- **AGV仓储调度**：四层调度架构（WMS→WES→Fleet→Simulation），含聚类、TSP、CP-SAT全局优化
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
- **VLM视觉理解**：支持Qwen2-VL和Qwen3.5-VLM两种模型，可动态切换
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
WMS层：订单生成、库存管理、任务分解
  ↓
WES层：方向感知聚类（精确batch键分组）
  ↓
Fleet层：CP-SAT全局分配 → 簇间TSP排序 → 逐簇TSP排序 → 路径规划
  ↓
Simulation层：AGV仿真执行、充电调度、指标统计
```

### 调度流程

```
随机/VLM工单 → 任务分解(TransportTask)
  → 聚类(按精确dest/pick分组 → 空间合并 → 容量拆分)
  → CP-SAT分配(簇→AGV, 最小化makespan)
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
| M4 CP-SAT | OR-Tools CP-SAT | 全局簇→AGV分配，最小化makespan |

### 消融实验结果

10组随机种子（42, 123, 456, 789, 2024, 3141, 6666, 9999, 12345, 54321）均值：

| 实验 | makespan | 距离 | 边际提升 |
|------|----------|------|---------|
| Baseline (无优化) | 1933 | 8616 | - |
| M1+M2 (+聚类) | 1033 | 3790 | 46.5% |
| M1+M2+M3 (+TSP) | 643 | 1849 | 37.8% |
| M1+M2+M3+M4 (+CP-SAT) | 590 | 1700 | 8.2% |
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

# 消融实验（4级对比）
python main_simulation.py --ablation
```
python main_simulation.py --animate medium_57x47_cluster 40
### 仓库模块结构

```
src/warehouse/
  models.py              - Pydantic v2 数据模型
  maps/
    base.py              - 地图注册基类
    medium_57x47.py      - 57×47 仓库地图定义
  wms/
    config.py            - 全局配置（Pydantic Settings）
    inventory.py         - 库存管理
    order_manager.py     - 工单生成（随机/VLM）
  wes/
    task_decomposer.py   - 任务分解
    clustering.py        - 精确batch键聚类
  fleet/
    map_builder.py       - 仓库地图构建（区域、端口、通道）
    pathfinding.py       - A*路径规划（方向感知+缓存）
    tsp.py               - OR-Tools TSP（双向batch）
    allocator.py         - CP-SAT全局分配 + 贪心降级
    charging.py          - 充电调度
    fleet_manager.py     - Fleet层总编排
  simulation/
    agv.py               - AGV仿真模型
    simulator.py         - 仿真执行引擎
    metrics.py           - 指标统计
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
```

---

## 港口指令解析详细说明

### vLLM 服务器管理

vLLM 服务器需独立启动，多个程序可共享使用：

```bash
python start_vlm_server.py     # 启动（根据 VLM_MODEL_TYPE 自动选择模型）
python status_vlm_server.py    # 查看状态
python stop_vlm_server.py      # 停止
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
| `CP_SAT_TIME_LIMIT` | 30 | CP-SAT求解时限(秒) |
| `RANDOM_SEED` | 42 | 随机种子 |

消融开关（`AblationFlags`）：
- `enable_path_cache`：M1 路径缓存
- `enable_clustering`：M2 聚类
- `enable_tsp`：M3 TSP排序
- `enable_cp_sat`：M4 CP-SAT全局分配

---

## 项目结构

```
wh_graphrag_re/
├── main_interaction.py       # 港口指令解析入口
├── main_simulation.py        # AGV调度仿真入口
├── main_rag.py               # RAG测试CLI
├── start_vlm_server.py       # vLLM服务器启动
├── stop_vlm_server.py        # vLLM服务器停止
├── status_vlm_server.py      # vLLM服务器状态
├── src/
│   ├── asr/whisper.py        # Whisper ASR
│   ├── vlm/                  # VLM模块（router + qwen2 + qwen35 + server）
│   ├── parser/parser.py      # PortInstruction解析器
│   ├── rag/                  # RAG模块（manager + traditional + graph）
│   ├── common/               # 配置、Reranker、工具函数
│   └── warehouse/            # AGV调度系统（见上方模块结构）
├── data/
│   ├── knowledge_base/       # 港口设备知识库
│   ├── vector_db/            # 向量数据库
│   └── graph_db/             # 图谱数据库
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

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件
