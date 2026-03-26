# wh_graphrag_re - All-in-VLM 多模态AI港口指令解析系统

基于 Python 的多模态AI系统，集成了语音识别、视觉语言模型、结构化解析和RAG知识检索，专门用于处理港口/海事领域的多模态指令。

## 项目特色

- 🎯 **All-in-VLM架构**：单一VLM模型处理多模态输入+RAG增强
- 🚀 **vLLM高性能推理**：PagedAttention优化，推理速度提升30-50%
- 🧠 **双模式RAG**：传统向量检索 + GraphRAG知识图谱
- 🔊 **多模态输入**：音频、文本、图像统一处理
- 📊 **结构化输出**：Pydantic模型确保输出质量
- ⚡ **自动服务器管理**：vLLM服务器自动启停，健康检查

## 🌟 核心特性

### 多模态输入支持
- **音频输入**：支持实时录音（5秒）和音频文件（WAV、MP3、M4A、FLAC、OGG）
- **文本输入**：直接输入文本指令或文本文件
- **图像输入**：支持图片分析（JPG、PNG、BMP、WebP）

### 智能解析引擎
- **ASR语音识别**：基于OpenAI Whisper large-v3-turbo，支持中文
- **VLM视觉理解**：支持Qwen2-VL和Qwen3.5-VLM两种模型，可动态切换
- **vLLM高性能推理**：使用vLLM引擎，PagedAttention优化推理速度
- **智能提示优化**：系统提示词包含型号与缩写识别、严格参考信息等优化
- **结构化输出**：解析为标准化的港口指令格式（Pydantic模型）

### RAG知识增强
- **传统RAG**：基于BGE-M3向量和BM25混合检索
- **GraphRAG**：知识图谱关系推理，支持多跳检索
- **动态切换**：运行时可启用/禁用RAG功能
- **智能分块**：语义分割和Markdown专用分块
- **统一管理**：UnifiedRAGManager提供单一入口管理两种RAG模式
- **上下文格式化**：支持多种参考格式（【参考1】、带评分等）

### 高级功能
- **重排序**：使用BGE-reranker-v2-m3优化结果
- **自适应检索**：三级阈值降级机制
- **多格式支持**：PDF、Word、Excel、Markdown等文档
- **实时交互**：友好的命令行界面

## 📊 系统架构

```
输入 (Audio/Text/Image)
  ↓
ASR模块 (Whisper) → 语音转文字（可选）
  ↓
VLM模块 (Qwen2-VL / Qwen3.5-VL) + vLLM服务器 + RAG上下文 → 结构化JSON生成
  ↓
解析器 (Pydantic) → 验证并提取PortInstruction模型
  ↓
PortInstruction结构化输出
```

**技术栈亮点：**
- **vLLM推理引擎**：PagedAttention优化，推理速度提升30-50%
- **OpenAI兼容API**：VLM客户端通过标准API与vLLM服务器通信
- **自动服务器管理**：启动、停止、健康检查全自动化

## 🚀 快速开始

### 1. 环境要求

- Python 3.8+
- PyTorch 2.0+（支持CUDA 12.4）
- FFmpeg（音频处理）
- 可选：sounddevice（实时录音）

### 2. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/sunofch/wh_ai.git
cd wh_ai

# 安装核心依赖
pip install -r requirements.txt

# 安装PyTorch（推荐CUDA 12.4）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# 安装FFmpeg（Linux）
sudo apt-get install ffmpeg

# 安装FFmpeg（Windows）
winget install "FFmpeg (Essentials Build)"

# 安装Qwen依赖
pip install qwen-vl-utils>=0.0.4

# 安装vLLM（高性能推理引擎）
pip install vllm>=0.6.1

# 可选：实时录音支持
pip install sounddevice soundfile numpy
```

### 3. 环境配置

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件
nano .env
```

**必需配置：**
```bash
# GraphRAG功能需要DeepSeek API Key
GRAPH_RAG_DEEPSEEK_API_KEY=your-api-key-here
```

**vLLM配置（可选）：**
```bash
# vLLM服务器配置
VLLM_SERVER_ENABLED=true
VLLM_SERVER_HOST=localhost
VLLM_SERVER_BASE_PORT=8000
VLLM_SERVER_GPU_MEM_UTIL=0.9
VLLM_SERVER_LIMIT_MM_PER_PROMPT={"image": 4, "video": 0}
```

**vLLM说明：**
- 系统使用vLLM进行高性能推理，自动管理服务器生命周期
- 首次运行会自动下载模型（Qwen2-VL-2B约5GB）
- GPU内存建议：8GB+（Qwen2-VL-2B），16GB+（Qwen3.5-VL）
- 如遇GPU内存不足，可降低 `VLLM_SERVER_GPU_MEM_UTIL` 或 `VLM_MAX_MODEL_LEN`

### 4. 准备知识库

将港口设备文档放入 `data/knowledge_base/` 目录：
```bash
# 支持格式：.md, .txt, .json, .yaml, .pdf, .docx, .xlsx
# 示例文档（已包含）：
# - conveyor_parts.md (传送带备件)
# - port_electrical_parts.md (电气备件)
# - port_hydraulic_parts.md (液压备件)
# - reach_stacker_parts.md (堆取机备件)
# - rtg_crane_parts.md (轮胎吊备件)
# - shore_crane_parts.md (岸桥备件)
```

## 🎯 使用方法

### 1. 交互式模式（推荐）

```bash
python main_interaction.py
```

**交互命令：**
- 输入文本指令：`需要更换3号传送带的电机`
- 输入文件路径：拖入图片/音频文件到终端
- 实时录音：输入 `r` 并按Enter（5秒录音）
- RAG管理：
  - `rag:status` - 查看RAG状态
  - `rag:enable` - 启用RAG
  - `rag:disable` - 禁用RAG
  - `rag:rebuild` - 重建知识库索引

### 2. 单次测试

```bash
# 文本指令
python main_interaction.py --text "需要5个电机，紧急"

# 图片分析
python main_interaction.py --image equipment_photo.jpg

# 音频转录
python main_interaction.py --audio command_audio.wav
```

### 3. RAG测试系统

```bash
python main_rag.py
```

提供传统RAG和GraphRAG两种模式的选择界面，支持：
- 传统RAG：向量检索 + BM25混合检索
- GraphRAG：知识图谱检索 + 多跳推理

## 📋 输出格式

系统输出标准化的 `PortInstruction` 对象：

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

**字段说明**：
- `part_name`: 备件名称（中文名称）
- `quantity`: 所需数量
- `model`: 型号规格
- `installation_equipment`: 安装设备名称
- `location`: 存放或安装位置
- `description`: 详细描述
- `action_required`: 所需操作（更换/维修/检查等）

## ⚙️ 配置说明

### 环境变量配置（.env）

```ini
# 模型配置
ASR_MODEL=large-v3-turbo
ASR_DEVICE=auto
ASR_LANGUAGE=zh

# VLM模型配置
VLM_MODEL=Qwen/Qwen2-VL-2B-Instruct
VLM_DEVICE=auto
VLM_MAX_TOKENS=512

# Qwen3.5-VLM配置
VLM35_MODEL=Qwen/Qwen3.5-9B
VLM35_DEVICE=auto
VLM35_MAX_TOKENS=4096

# VLM模型类型选择 (qwen2 或 qwen35)
VLM_MODEL_TYPE=qwen2

# RAG配置
RAG_ENABLED=true
RAG_GRAPH_ENABLED=true
RAG_EMBEDDING_MODEL=BAAI/bge-m3
RAG_TOP_K=3

# GraphRAG配置（需要DeepSeek API Key）
GRAPH_RAG_LLM_PROVIDER=deepseek
GRAPH_RAG_DEEPSEEK_API_KEY=your-api-key-here
GRAPH_RAG_DEEPSEEK_MODEL=deepseek-chat
```

### 关键配置项

- **备件名称**：解析失败时的默认名称（config.parser.fallback_part_name）
- **描述前缀**：规则解析时的描述前缀（config.parser.fallback_description_prefix）
- **检索模式**：fixed/adaptive/hybrid（推荐hybrid）
- **RAG上下文格式**：支持多种参考格式（默认【参考1】格式）
- **VLM模型选择**：通过 `VLM_MODEL_TYPE` 环境变量选择模型
  - `qwen2`：使用 Qwen2-VL-2B-Instruct（默认，更快）
  - `qwen35`：使用 Qwen3.5-9B（更强大但更慢）

### VLM模型切换

系统支持在 Qwen2-VL 和 Qwen3.5-VLM 之间动态切换：

**方法1：环境变量**
```bash
# 使用 Qwen3.5-VLM
export VLM_MODEL_TYPE=qwen35
python main_interaction.py

# 使用 Qwen2-VL（默认）
export VLM_MODEL_TYPE=qwen2
python main_interaction.py
```

**方法2：.env文件**
```ini
# 在 .env 文件中设置
VLM_MODEL_TYPE=qwen35
```

**方法3：命令行**
```bash
VLM_MODEL_TYPE=qwen35 python main_interaction.py --text "需要5个电机"
```

**模型对比**：
- **Qwen2-VL-2B**：较小（~5GB），推理速度快，适合资源受限环境
- **Qwen3.5-9B**：更大（~18GB），推理能力更强，适合复杂场景

## 📂 项目结构

```
wh_graphrag_re/
├── main_interaction.py    # 主要交互入口（推荐）
├── main_rag.py            # RAG测试系统
├── src/
│   ├── asr.py            # Whisper语音识别
│   ├── vlm.py            # 统一VLM接口（支持模型切换）
│   ├── qwen2vlm.py       # Qwen2-VL实现
│   ├── qwen35vlm.py      # Qwen3.5-VLM实现
│   ├── parser.py         # 结构化解析器
│   ├── rag.py            # 传统RAG检索
│   ├── rag_manager.py    # RAG统一管理器
│   ├── graph_rag.py      # GraphRAG图谱检索
│   ├── graph_extractors.py # 图谱提取器
│   ├── config.py         # 配置管理（Pydantic）
│   └── utils.py          # 工具函数
├── data/
│   ├── knowledge_base/   # 知识库文档
│   ├── vector_db/        # 向量数据库
│   └── graph_db/         # 图谱数据库
├── .env.example          # 环境变量模板
├── requirements.txt      # 依赖列表
└── README.md             # 项目文档
```

## 🔧 API使用示例

### 基本使用

```python
from src.asr import get_asr_instance
from src.vlm import get_vlm_instance  # 统一VLM接口
from src.parser import PortInstructionParser, PortInstruction

# 创建解析器（模型使用LRU缓存自动管理）
asr = get_asr_instance()
vlm = get_vlm_instance()  # 自动根据配置选择 Qwen2-VL 或 Qwen3.5-VLM
parser = PortInstructionParser()

# 音频转文字
audio_text = asr.transcribe("audio.wav")

# 获取格式化指令（Schema）
format_instructions = parser.get_format_instructions()

# 多模态解析（VLM + RAG）
vlm_result = vlm.extract_structured_info(
    text=audio_text,
    format_instructions=format_instructions,
    image=None,  # 可选图片路径
    enable_rag=True  # 启用RAG增强
)

# 解析输出
result = parser.parse_output(
    vlm_result=vlm_result,
    raw_text=audio_text
)
print(result.to_dict())
# 输出示例：{
#   "part_name": "传送带电机",
#   "quantity": 5,
#   "model": "YVF2-132S-4",
#   ...
# }
```

### RAG集成

```python
from src.rag_manager import initialize_rag_system, get_unified_rag_manager

# 初始化RAG系统（选择模式）
success = initialize_rag_system(mode='graph')  # 或 'traditional'
if success:
    # 获取统一RAG管理器
    rag_manager = get_unified_rag_manager()

    # 检索相关知识
    results = rag_manager.retrieve("传送带维修")

    # 格式化上下文（自动适配格式）
    context = rag_manager.format_context(results)

    # 查看状态
    status = rag_manager.get_status()
    print(f"模式: {status['mode']}, 可用: {status['available']}")

    # 动态切换模式
    rag_manager.initialize(mode='traditional')
```

### GraphRAG使用

```python
from src.rag_manager import initialize_rag_system, get_unified_rag_manager

# 使用统一管理器初始化GraphRAG
success = initialize_rag_system(mode='graph')
if success:
    rag_manager = get_unified_rag_manager()

    # 检查是否为GraphRAG模式
    if rag_manager.is_graph_mode:
        # 执行检索
        results = rag_manager.retrieve("电机型号")

        # 格式化上下文
        context = rag_manager.format_context(results)

        # 清除缓存（GraphRAG特有功能）
        rag_manager.clear_cache()
```

## ⚠️ 重要说明

### 1. 编码问题
如果遇到GBK编码错误，使用：
```bash
python -X utf8 main_interaction.py
```

### 2. 模型下载
- 首次运行会自动下载模型（需要网络）
- BGE-M3：约2.3GB
- Qwen2-VL：约5GB
- 建议使用GPU加速

### 3. API配置
GraphRAG需要DeepSeek API Key（或其他兼容LLM）：
```bash
# 在.env中配置
GRAPH_RAG_DEEPSEEK_API_KEY=your-key-here
```

### 4. 性能优化
- 模型自动缓存（LRU策略）
- 音频内存处理，无临时文件
- RAG查询结果缓存

## 📈 系统优势

1. **端到端处理**：从原始输入到结构化输出
2. **多模态融合**：同时处理音频、文本、图像
3. **知识增强**：双模式RAG（传统向量+知识图谱）
4. **统一管理**：UnifiedRAGManager单一入口管理RAG
5. **智能降级**：解析失败时自动降级到规则提取
6. **易于扩展**：模块化设计，方便添加新功能

## 🔍 故障排查

### 常见问题

1. **模型加载失败**
   - 检查网络连接和磁盘空间（BGE-M3: ~2.3GB, Qwen2-VL: ~5GB）
   - 尝试使用CPU模式：设置 `ASR_DEVICE=cpu` 和 `VLM_DEVICE=cpu`
   - 验证PyTorch版本兼容性（推荐CUDA 12.4）

2. **RAG检索失败**
   - 确认 `data/knowledge_base/` 目录存在且包含.md文档
   - 检查BGE-M3模型是否正确下载
   - 尝试运行 `rag:rebuild` 重建索引
   - GraphRAG需确认 `GRAPH_RAG_DEEPSEEK_API_KEY` 配置正确

3. **录音功能异常**
   - 安装依赖：`pip install sounddevice soundfile numpy`
   - 检查系统麦克风权限
   - 可降级为文件上传方式

4. **编码问题（GBK错误）**
   - 使用UTF-8模式运行：`python -X utf8 main_interaction.py`
   - 检查终端编码设置

5. **JSON解析失败**
   - 系统会自动使用 `json_repair` 修复常见格式问题
   - 失败时自动降级到规则解析
   - 可检查VLM输出的原始响应进行调试

## 🤝 贡献指南

欢迎提交Issue和Pull Request！

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/new-feature`
3. 提交更改：`git commit -m 'Add new feature'`
4. 推送分支：`git push origin feature/new-feature`
5. 提交Pull Request

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

**All-in-VLM** - 一个强大的多模态AI系统，让港口指令处理更加智能和高效！
