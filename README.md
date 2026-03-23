# wh_graphrag_re - All-in-VLM 多模态AI港口指令解析系统

基于 Python 的多模态AI系统，集成了语音识别、视觉语言模型、结构化解析和RAG知识检索，专门用于处理港口/海事领域的多模态指令。

## 项目特色

- 🎯 **All-in-VLM架构**：单一VLM模型处理多模态输入+RAG增强
- 🧠 **双模式RAG**：传统向量检索 + GraphRAG知识图谱
- 🔊 **多模态输入**：音频、文本、图像统一处理
- 📊 **结构化输出**：Pydantic模型确保输出质量
- ⚡ **高性能**：模型缓存、内存处理、查询优化

## 🌟 核心特性

### 多模态输入支持
- **音频输入**：支持实时录音（5秒）和音频文件（WAV、MP3、M4A、FLAC、OGG）
- **文本输入**：直接输入文本指令或文本文件
- **图像输入**：支持图片分析（JPG、PNG、BMP、WebP）

### 智能解析引擎
- **ASR语音识别**：基于OpenAI Whisper large-v3-turbo，支持中文
- **VLM视觉理解**：使用Qwen2-VL-2B-Instruct处理图像和文本
- **结构化输出**：解析为标准化的港口指令格式（Pydantic模型）

### RAG知识增强
- **传统RAG**：基于BGE-M3向量和BM25混合检索
- **GraphRAG**：知识图谱关系推理，支持多跳检索
- **动态切换**：运行时可启用/禁用RAG功能
- **智能分块**：语义分割和Markdown专用分块

### 高级功能
- **重排序**：使用BGE-reranker-v2-m3优化结果
- **自适应检索**：三级阈值降级机制
- **多格式支持**：PDF、Word、Excel、Markdown等文档
- **实时交互**：友好的命令行界面

## 📊 系统架构

```
输入 (Audio/Text/Image)
  ↓
ASR模块 → 语音转文字（可选）
  ↓
上下文构建器 → 整合所有输入
  ↓
RAG模块 → 检索相关知识（可选）
  ↓
VLM模块 → 生成结构化指令
  ↓
解析器 → 提取Pydantic模型
  ↓
PortInstruction结构化输出
```

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

# 可选：实时录音支持
pip install sounddevice soundfile numpy
```

### 3. 环境配置

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件
# 至少需要配置 DeepSeek API Key 用于 GraphRAG
nano .env
```

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
  "urgency": "高",
  "location": "3号传送带",
  "description": "需要更换电机",
  "action_required": "更换",
  "confidence": 0.95
}
```

## ⚙️ 配置说明

### 环境变量配置（.env）

```ini
# 模型配置
ASR_MODEL=large-v3-turbo
ASR_DEVICE=auto
ASR_LANGUAGE=zh
VLM_MODEL=Qwen/Qwen2-VL-2B-Instruct
VLM_DEVICE=auto
VLM_MAX_TOKENS=512

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

- **置信度阈值**：解析成功的最低置信度（默认0.9）
- **紧急程度**：默认"中"，自动检测紧急关键词
- **备件名称**：解析失败时的默认名称
- **检索模式**：fixed/adaptive/hybrid（推荐hybrid）

## 📂 项目结构

```
wh_graphrag_re/
├── main_interaction.py    # 主要交互入口（推荐）
├── main_rag.py            # RAG测试系统
├── src/
│   ├── asr.py            # Whisper语音识别
│   ├── vlm.py            # Qwen2-VL视觉语言模型
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
from src.vlm import get_vlm_instance
from src.parser import PortInstructionParser, PortInstruction

# 创建解析器
asr = get_asr_instance()
vlm = get_vlm_instance()
parser = PortInstructionParser()

# 音频转文字
audio_text = asr.transcribe("audio.wav")

# 多模态解析
result = parser.parse_output(
    vlm_result={"content": "..."},
    raw_text=audio_text
)
print(result.to_dict())
```

### RAG集成

```python
from src.rag import get_rag_instance

# 初始化RAG
rag = get_rag_instance()
if rag:
    # 检索相关知识
    results = rag.retrieve("传送带维修")
    for result in results:
        print(f"相似度: {result['score']:.3f}")
        print(f"内容: {result['text']}")
```

### GraphRAG使用

```python
from src.graph_rag import get_graph_rag_instance

# 初始化GraphRAG
graph_rag = get_graph_rag_instance()
if graph_rag:
    # 图谱检索
    results = graph_rag.retrieve("电机型号")
    for result in results:
        print(f"内容: {result.text}")
        print(f"评分: {result.score}")
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
3. **知识增强**：RAG提供领域知识支持
4. **容错性强**：解析失败时自动降级
5. **易于扩展**：模块化设计，方便添加新功能

## 🔍 故障排查

### 常见问题

1. **模型加载失败**
   - 检查网络连接
   - 确认磁盘空间足够
   - 尝试使用CPU模式

2. **RAG检索失败**
   - 确认知识库目录存在且有文档
   - 检查embedding模型是否正确下载
   - 尝试重建索引

3. **录音功能异常**
   - 安装sounddevice：`pip install sounddevice`
   - 检查麦克风权限

4. **图片识别问题**
   - 确认图片格式支持
   - 检查图片路径正确
   - 提供清晰的图片

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
