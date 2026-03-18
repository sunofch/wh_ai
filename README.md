# wh_ai - 港口指令多模态AI解析系统

基于Python的多模态AI系统，集成了语音识别、视觉语言模型、结构化解析和RAG知识检索，用于处理港口/海事领域的多模态指令（音频、文本、图像）。

## 🚀 核心特性

- **多模态输入支持**：音频、文本、图像三种输入方式
- **智能语音识别**：基于Whisper的实时语音转文字
- **视觉语言理解**：使用Qwen2-VL-2B-Instruct处理图像
- **RAG知识检索**：基于BGE-M3向量和BM25混合检索
- **GraphRAG增强**：知识图谱关系推理，支持多跳检索
- **结构化输出**：解析为标准化的港口指令格式
- **多种运行模式**：交互式、CLI、GraphRAG专用模式

## 📋 系统架构

```
输入 (Audio/Text/Image)
  ↓
ASR模块 (音频转文字) → 转写文本
  ↓
上下文构建器 → 整合所有输入
  ↓
RAG模块 → 从向量数据库检索相关知识
  ↓
VLM模块 (Qwen2-VL) → 生成结构化指令
  ↓
解析器 → 提取并验证Pydantic模型
  ↓
结构化指令输出
```

## 🛠️ 快速开始

### 1. 环境要求

- Python 3.8+
- CUDA 12.4（可选，用于GPU加速）
- FFmpeg（音频处理必需）

### 2. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/sunofch/wh_ai.git
cd wh_ai

# 安装核心依赖
pip install -r requirements.txt

# 安装PyTorch（支持CUDA 12.4）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# 安装FFmpeg（Windows）
winget install "FFmpeg (Essentials Build)"

# 安装Qwen特定依赖
pip install qwen-vl-utils>=0.0.4
```

### 3. 配置环境

```bash
# 复制环境配置模板
cp .env.example .env

# 编辑.env文件，配置API密钥和模型参数
nano .env
```

### 4. 准备知识库

将港口设备相关的文档放入 `data/knowledge_base/` 目录：
- 支持格式：`.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.pdf`, `.docx`, `.xlsx`
- 示例文件已包含：
  - conveyor_parts.md - 传送带备件
  - port_electrical_parts.md - 电气备件
  - port_hydraulic_parts.md - 液压备件
  - reach_stacker_parts.md - 堆取机备件
  - rtg_crane_parts.md - 轮胎吊备件
  - shore_crane_parts.md - 岸桥备件

## 🎯 运行方式

### 1. 交互式模式（推荐）

```bash
python main_Interaction.py
```

**交互命令：**
- 直接输入文本指令并按Enter
- 输入文件路径（图片、音频、文本文件）
- 输入 `r` 并按Enter进行5秒实时录音
- `rag:status` - 查看RAG模块状态
- `rag:enable` / `rag:disable` - 切换RAG增强
- `rag:rebuild` - 重建知识库索引
- `rag:graph` - 查看GraphRAG统计（启用时）

### 2. GraphRAG专用模式

```bash
# 查看帮助
python main_graphrag_cli.py --help

# 交互模式
python main_graphrag_cli.py

# 单次查询
python main_graphrag_cli.py --query "港口设备有哪些类型"

# 查看图谱统计
python main_graphrag_cli.py --stats

# 重建图谱索引
python main_graphrag_cli.py --rebuild

# 指定返回数量
python main_graphrag_cli.py --query "查询内容" --top-k 5
```

### 3. RAG测试模式

```bash
python main_rag_cli.py
```

### 4. 单次测试

```bash
# 文本指令测试
python main_Interaction.py --text "更换3号传送带的电机"

# 图像输入测试
python main_Interaction.py --image equipment_image.jpg

# 音频文件测试
python main_Interaction.py --audio audio_command.wav
```

## 📊 功能模块详解

### 语音识别 (ASR)
- **模型**：Whisper large-v3-turbo
- **功能**：实时录音（5秒）和文件转录
- **支持格式**：WAV, MP3, M4A, FLAC, OGG
- **优化**：内存处理，无临时文件

### 视觉语言模型 (VLM)
- **模型**：Qwen2-VL-2B-Instruct
- **功能**：处理图像+文本输入，生成结构化描述
- **输出**：符合Pydantic模型的标准化指令

### RAG知识检索
- **嵌入模型**：BGE-M3（2.3GB，多语言支持）
- **存储方式**：SimpleVectorStore（JSON，无文件锁）
- **检索模式**：
  - `fixed` - 固定阈值
  - `adaptive` - 自适应阈值（三级降级）
  - `hybrid` - 混合检索（BM25 + 向量）

### GraphRAG图检索
- **图索引**：PropertyGraphIndex（无需Neo4j）
- **实体类型**：港口设备、系统机构、备件零件等
- **关系类型**：包含、属于、规格为、存放于、别名为
- **提取器**：DynamicLLMPathExtractor（推荐）
- **查询缓存**：TTL 3600秒，最大100条

### 结构化解析
- **主要方式**：LangChain + Pydantic
- **降级方式**：正则表达式提取
- **输出字段**：备件名称、数量、紧急程度、位置、描述、操作要求

## ⚙️ 配置说明

所有配置通过 `config.ini` 或 `.env` 文件管理：

### 模型配置
```ini
[models]
asr_model = large-v3-turbo
asr_device = auto
asr_language = zh
vlm_model = Qwen/Qwen2-VL-2B-Instruct
vlm_device = auto
vlm_max_tokens = 512
```

### RAG配置
```ini
[rag]
enabled = true
graph_enabled = true
embedding_model = BAAI/bge-m3
top_k = 3
mode = hybrid
```

### GraphRAG配置
```ini
[graph_rag]
extractor_type = dynamic
max_triplets_per_chunk = 15
entity_hints = 港口设备,系统机构,备件零件,规格型号,存放库位
relation_hints = 包含,属于,规格为,存放于,别名为
```

## 🗂️ 项目结构

```
wh_ai/
├── main_Interaction.py    # 主要交互入口
├── main_graphrag_cli.py   # GraphRAG专用CLI
├── main_rag_cli.py        # RAG测试CLI
├── src/
│   ├── asr.py             # 语音识别模块
│   ├── vlm.py             # 视觉语言模型
│   ├── parser.py          # 结构化解析器
│   ├── rag.py             # RAG知识检索
│   ├── graph_rag.py       # GraphRAG图检索
│   ├── graph_extractors.py # 图谱提取器
│   ├── config.py          # 配置管理
│   └── utils.py           # 工具函数
├── data/
│   ├── knowledge_base/    # 知识库文档
│   └── vector_db/         # 向量数据库
│       └── graph_db/     # 图谱数据库
├── models/               # 模型缓存目录
├── output/              # 输出文件目录
└── requirements.txt     # 依赖列表
```

## 🔧 API使用示例

### RAG检索
```python
from src.rag import get_rag_instance

rag = get_rag_instance()
if rag:
    results = rag.retrieve("查询港口设备维修指南")
    for result in results:
        print(f"{result['score']:.3f}: {result['text']}")
```

### GraphRAG查询
```python
from src.graph_rag import get_graph_rag_instance

graph_rag = get_graph_rag_instance()
if graph_rag:
    results = graph_rag.retrieve("传送带备件型号")
    stats = graph_rag.get_graph_stats()
    print(f"节点数: {stats['node_count']}, 关系数: {stats['relation_count']}")
```

## 🚨 注意事项

1. **编码问题**：如果出现gbk编码错误，使用：
   ```bash
   python -X utf8 main_Interaction.py
   ```

2. **模型大小**：
   - BGE-M3嵌入模型：约2.3GB
   - Qwen2-VL模型：约5GB
   - 建议使用GPU加速

3. **网络要求**：
   - 下载模型需要联网
   - 使用API时需要配置正确的密钥

4. **内存优化**：
   - 系统使用LRU缓存避免重复加载模型
   - 音频数据内存处理，无临时文件

## 📈 性能优化

- **查询缓存**：GraphRAG结果缓存，减少LLM调用
- **并行处理**：图谱提取支持多线程
- **自适应阈值**：根据查询质量自动调整检索策略
- **重排序**：使用BGE-reranker提升结果相关性

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/新功能`
3. 提交更改：`git commit -m '添加新功能'`
4. 推送分支：`git push origin feature/新功能`
5. 提交Pull Request

## 📄 许可证

本项目遵循 MIT 许可证。详情请见 [LICENSE](LICENSE) 文件。

## 📞 支持

如有问题或建议，请：
1. 查看文档和FAQ
2. 提交Issue
3. 联系维护者

---

**注意**：本项目主要用于港口和海事领域的智能指令处理，可根据具体需求进行定制化开发。