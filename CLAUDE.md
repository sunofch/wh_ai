# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **wh_graphrag_re**, a multi-modal AI port instruction parsing system that combines:
- **All-in-VLM Architecture**: Single Vision Language Model handles multiple input types + RAG enhancement
- **vLLM High-Performance Inference**: Uses vLLM engine with PagedAttention for 30-50% speed improvement
- **Dual-Mode RAG**: Traditional vector retrieval (BGE-M3 + BM25) and GraphRAG knowledge graph
- **Multi-modal Inputs**: Audio (Whisper ASR), Text, Images (Qwen2-VL / Qwen3.5-VL)
- **Dynamic Model Selection**: Runtime switching between Qwen2-VL and Qwen3.5-VLM via config
- **Structured Output**: Pydantic models ensure data quality for port instruction parsing

**Application Domain**: Port/maritime equipment spare parts and maintenance instructions in Chinese.

## Common Commands

### Running the Application

```bash
# Main interactive mode (recommended for most work)
python main_interaction.py

# Single text instruction
python main_interaction.py --text "需要5个电机，紧急"

# Image analysis
python main_interaction.py --image equipment_photo.jpg

# Audio transcription
python main_interaction.py --audio command_audio.wav

# RAG testing system (choose traditional or graph mode)
python main_rag.py
```

### vLLM Server Management

```bash
# 启动 vLLM 服务器（开发时必须先启动）
python start_vlm_server.py

# 查看服务器状态
python status_vlm_server.py

# 停止 vLLM 服务器
python stop_vlm_server.py
```

**重要**：运行 `main_interaction.py` 之前必须先启动 vLLM 服务器！

### Interactive Commands

When running `main_interaction.py`, these commands are available:
- Input text directly
- Drag and drop image/audio files
- Type `r` and press Enter for 5-second audio recording
- `rag:status` - View RAG status
- `rag:enable` / `rag:disable` - Toggle RAG
- `rag:rebuild` - Rebuild knowledge base index

### Environment Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Install PyTorch with CUDA support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Copy and configure environment variables
cp .env.example .env
nano .env
```

**Critical Configuration**: Set `GRAPH_RAG_DEEPSEEK_API_KEY` in `.env` for GraphRAG to work.

### Encoding Issues

If you encounter GBK encoding errors:
```bash
python -X utf8 main_interaction.py
```

## High-Level Architecture

### vLLM 服务器管理

**重要变更**：vLLM 服务器现在独立于业务程序运行。

**启动流程**：
1. 用户运行 `python start_vlm_server.py` 启动服务器
2. 服务器根据 `.env` 配置选择模型（qwen2/qwen35）
3. 服务器启动后在后台运行，监听端口 8000 或 8001
4. 服务器进程信息保存到 `.vlm_server.pid`

**业务程序连接**：
1. 业务程序启动时检查服务器运行状态
2. 如果服务器未运行，显示错误并退出
3. 如果服务器运行中，正常连接使用

**停止流程**：
- 用户运行 `python stop_vlm_server.py` 或按 `Ctrl+C` 停止服务器
- 清理 `.vlm_server.pid` 文件

### Data Flow Pipeline

```
Input (Audio/Text/Image)
  ↓
ASR Module (Whisper) → Speech-to-Text (if audio)
  ↓
VLM Module (Qwen2-VL / Qwen3.5-VL) + vLLM Server + RAG Context → Structured JSON Generation
  ↓
Parser (Pydantic) → Validate & Extract PortInstruction Model
  ↓
PortInstruction Structured Output
```

**vLLM Architecture:**
- VLM Client (OpenAI SDK) → HTTP → vLLM Server (localhost:8000/8001)
- Manual server lifecycle management: `start_vlm_server.py` / `stop_vlm_server.py` / `status_vlm_server.py`
- PID file `.vlm_server.pid` for process tracking
- PagedAttention optimization for high-throughput inference

### Dual-Mode RAG System

The system supports **two independent RAG modes** selected at runtime:

1. **Traditional RAG** (`src/rag.py`):
   - Vector retrieval with BGE-M3 embeddings
   - Hybrid BM25 + vector search
   - Reranking with BGE-reranker-v2-m3
   - Three-tier adaptive threshold fallback

2. **GraphRAG** (`src/graph_rag.py`):
   - Knowledge graph with PropertyGraphIndex
   - Entity-relationship extraction (DeepSeek LLM)
   - Multi-hop reasoning and synonym retrieval
   - Requires DeepSeek API key

**Switching Modes**: Set `RAG_GRAPH_ENABLED=true/false` in `.env` or via `rag_manager.initialize(mode='graph'/'traditional')`.

### Reranker System

The system uses a **unified Reranker module** (`src/reranker.py`) that serves both RAG modes:

- **BGE-reranker-v2-m3**: State-of-the-art cross-encoder for result reranking
- **Singleton Pattern**: Global `RerankerManager` instance shared across all modules
- **Flexible Integration**:
  - Traditional RAG: Enabled via `RAG_RERANK_ENABLED=true`
  - GraphRAG: Enabled via `GRAPH_RERANK_ENABLED=true`
- **Configuration**:
  - `RAG_RERANK_TOP_K` / `GRAPH_RERANK_TOP_K`: Candidate count for reranking (default: 10)
  - `RAG_RERANK_FINAL_TOP_K` / `GRAPH_RERANK_FINAL_TOP_K`: Final result count (default: 3)
  - `RAG_RERANK_DEVICE` / `GRAPH_RERANK_DEVICE`: Device selection (auto/cuda/cpu)

**Usage**:
```python
# 方式 1: 详细导入（推荐，语义明确）
from src.common.reranker import get_reranker_instance

# 方式 2: 便捷导入（向后兼容）
from src.reranker import get_reranker_instance

reranker = get_reranker_instance()
results = reranker.rerank(query, candidates, top_k=3)
# Results now contain 'rerank_score' field and are sorted by relevance
```

### Module Structure

**Entry Points**:
- `main_interaction.py`: Main CLI interface for instruction parsing
- `main_rag.py`: RAG testing CLI with mode selection

**Core Processing** (`src/`):
- `src/common/config.py`: **Pydantic Settings** - All configuration from environment variables, grouped by domain (ASR, VLM, RAG, vLLM server, etc.)
- `src/vlm/router.py`: **Unified VLM Entry** - Dynamic model selection router (Qwen2-VL ↔ Qwen3.5-VL)
- `src/vlm/qwen2.py`: Qwen2VLM - vLLM client implementation using OpenAI SDK
- `src/vlm/qwen35.py`: Qwen35VLM - vLLM client implementation using OpenAI SDK
- `src/vlm/server.py`: **VLLMServerManager** - vLLM server lifecycle management (PID file management, health-check)
- `src/asr/whisper.py`: WhisperASR - Audio transcription with LRU caching
- `src/parser/parser.py`: PortInstructionParser - Schema definition + rule-based fallback
- `src/rag/manager.py`: **UnifiedRAGManager** - Single entry point for both RAG modes
- `src/rag/traditional.py`: RAGRetriever - Traditional vector + BM25 retrieval
- `src/rag/graph.py`: GraphRAGRetriever - Knowledge graph retrieval
- `src/common/reranker.py`: **RerankerManager** - Unified BGE Reranker service (singleton)
- `src/common/utils.py`: Device selection and image conversion utilities
- `src/rag/graph_extractors.py`: Knowledge graph extractors for GraphRAG

### Key Design Patterns

**Singleton Pattern with LRU Cache**:
- `get_asr_instance()`, `get_vlm_instance()`, `get_vlm_server_manager()`, `get_reranker_instance()`
- Models/servers loaded once and cached in memory
- Prevents GPU OOM from multiple model loads

**Configuration via Pydantic Settings**:
- All config in `src/config.py` using Pydantic BaseSettings
- Environment variables mapped with aliases (e.g., `ASR_MODEL` → `asr.model`)
- Type-safe with validation and defaults
- **New**: VLLMServerConfig for vLLM server settings

**vLLM Server Management**:
- `VLLMServerManager` handles server lifecycle (start/stop/health-check)
- Automatic port conflict detection and error handling
- Graceful shutdown via `atexit` registration
- Health check with retry logic for reliability

**Unified VLM Interface**:
- `src/vlm.py` provides **model-agnostic router** - imports correct VLM based on `VLM_MODEL_TYPE`
- Runtime switching: Set `VLM_MODEL_TYPE=qwen2` or `VLM_MODEL_TYPE=qwen35` in `.env`
- Both implementations use **identical interface** via vLLM server (OpenAI-compatible)
- `VLM_NAME` constant exposes active model for logging/debugging

**Unified RAG Manager**:
- `rag_manager.initialize(mode)` selects traditional or graph mode
- Single `retrieve()` interface regardless of mode
- Dynamic enable/disable via `set_enabled()`

**RAG Integration in VLM**:
- VLM directly retrieves RAG context in `extract_structured_info()`
- RAG context prepended to system prompt
- RAG can be toggled at runtime without model reload

### Data Models

**PortInstruction** (`src/parser.py`):
```python
part_name: Optional[str]  # 备件中文名称
quantity: Optional[int]   # 所需数量
model: Optional[str]      # 型号
installation_equipment: Optional[str]  # 安装设备
location: Optional[str]   # 备件安装设备的地点
description: Optional[str]  # 用户指令中的其他重要信息
action_required: Optional[str]  # 行动：更换、维修、检查等
```

### Knowledge Base

Located in `data/knowledge_base/`:
- Markdown files containing port equipment spare parts terminology
- **Required format**: Chinese name, English name, abbreviation, model, installation equipment
- Files: `01_shore_crane_parts.md`, `02_rtg_crane_parts.md`, `03_reach_stacker_parts.md`, `04_port_electrical_parts.md`, `05_port_hydraulic_parts.md`, `06_conveyor_parts.md`

**Vector DB**: `data/vector_db/` (Traditional RAG embeddings)
**Graph DB**: `data/graph_db/` (GraphRAG property graph store)

## Important Constraints

### Device Selection
- Use `get_device("auto")` from `src/utils.py` for all GPU/CPU decisions
- Don't hardcode `"cuda"` - check `torch.cuda.is_available()`
- Model loading in `ASR`, `VLM`, and RAG modules respects this

### RAG Initialization
- RAG modules are **optional** - system works without them
- Check `HAS_RAG` flag before importing RAG modules
- GraphRAG requires valid `GRAPH_RAG_DEEPSEEK_API_KEY`
- Traditional RAG requires BGE-M3 model download (~2.3GB)

### Model Caching
- All model instances use `@lru_cache(maxsize=1)` on getter functions
- Never instantiate models directly in business logic
- Always use `get_*_instance()` functions

### Audio Handling
- ASR processes audio **in-memory** - no temporary files
- Default sample rate: 16kHz
- Supported formats: WAV, MP3, M4A, FLAC, OGG
- Real-time recording requires `sounddevice` library

### Parser Fallback
- VLM outputs validated with Pydantic
- If validation fails, rule-based regex parsing extracts basic info
- Fallback uses configurable defaults from `config.parser.*`

### vLLM 服务器约束
- **必须手动启动**：运行 `main_interaction.py` 之前必须先启动 vLLM 服务器
- **独立运行**：vLLM 服务器进程独立于业务程序运行
- **PID 文件管理**：进程信息保存在 `.vlm_server.pid`，不要手动删除
- **端口管理**：qwen2 使用端口 8000，qwen35 使用端口 8001
- **停止服务器**：使用 `stop_vlm_server.py` 或 Ctrl+C 停止

## Common Issues

**Model download on first run**:
- BGE-M3: ~2.3GB, Qwen2-VL: ~5GB
- Requires internet connection
- Cached in `./models/` directory

**GraphRAG not working**:
- Check `.env` has valid `GRAPH_RAG_DEEPSEEK_API_KEY`
- Ensure `RAG_GRAPH_ENABLED=true`
- Knowledge base must have markdown documents

**RAG retrieval fails**:
- Confirm `data/knowledge_base/` has `.md` files
- Check BGE-M3 model downloaded correctly
- Try `rag:rebuild` command to rebuild index

**Reranker not working**:
- Check if `RAG_RERANK_ENABLED=true` (for traditional RAG) or `GRAPH_RERANK_ENABLED=true` (for GraphRAG)
- Ensure `FlagEmbedding` library is installed: `pip install -U FlagEmbedging`
- BGE-reranker-v2-m3 model (~1.5GB) will download on first use
- Check if results contain `rerank_score` field to verify reranking is active

**Audio recording errors**:
- Install: `pip install sounddevice soundfile numpy`
- Check microphone permissions
- Fallback to file upload if recording fails

**vLLM server issues**:
- **Server startup timeout**: Check GPU availability with `nvidia-smi`, verify CUDA 12.4+. Default timeout: 180s (`VLLM_SERVER_STARTUP_TIMEOUT`)
- **Port already in use**: Change `VLLM_SERVER_BASE_PORT` in `.env` (default 8000)
- **GPU out of memory**: Lower `VLLM_SERVER_GPU_MEM_UTIL` (default 0.5) or reduce `VLM_MAX_MODEL_LEN`
- **Server not responding**: Check if vLLM process is running with `ps aux | grep vllm`
- **Model download slow**: First run downloads Qwen2-VL-2B (~5GB), be patient
- **Import errors**: Ensure `vllm>=0.6.1` and `openai>=1.0.0` are installed
