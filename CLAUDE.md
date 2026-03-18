# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 在编写和重构代码时，请遵循以下约定

1.禁止使用表情符号 (Emoji)：在代码注释、日志输出、提交信息或用户界面文本中，应严格使用纯文本表达逻辑或状态，避免使用表情符号。

2.避免过度设计 Fallback 机制：
- 应优先确保核心机制/原始逻辑的完整实现。
- 严禁设计多级嵌套的降级/兜底方案（Multi-level fallback），以防止掩盖真实的逻辑缺陷或增加维护复杂度。
- 若因技术限制无法实现预定机制，应立即停止尝试并向用户提出具体问题，说明阻碍因素。

3.代码编写完成后，必须在当前环境中运行并测试，严禁提交未经实际运行验证的"理论可行"代码。若测试失败或环境受限无法完成完整测试，必须在提交前告知具体原因，并寻求进一步指示。

## Project Overview

This is a Python-based multimodal AI system for parsing port instructions with RAG (Retrieval-Augmented Generation) support. The system ("All-in-VLM") combines speech recognition, vision-language models, structured parsing, and knowledge base retrieval to process maritime/port commands from multiple input modalities (audio, text, images).

**Tech Stack**: Python 3.x, PyTorch, Transformers, OpenAI Whisper, Qwen2-VL-2B-Instruct, LlamaIndex, SimpleVectorStore, BGE-M3 embeddings

## Development Commands

### Setup
```bash
# Install core dependencies
pip install -r requirements.txt

# Install PyTorch with CUDA 12.4 support (adjust if using different CUDA version)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Install FFmpeg (required for audio processing on Windows)
winget install "FFmpeg (Essentials Build)"

# Install Qwen-specific dependencies
pip install qwen-vl-utils>=0.0.4
```

### Running the Application

**Interactive Mode** (full console interface):
```bash
python main_Interaction.py
```

**GraphRAG CLI Mode** (dedicated GraphRAG testing):
```bash
python main_graphrag_cli.py
```

**RAG CLI Mode** (traditional RAG testing):
```bash
python main_rag_cli.py
```

**Single Test Mode**:
```bash
# Test with text instruction
python main_Interaction.py --text "指令文本"

# Test with image input
python main_Interaction.py --image 图片路径

# Test with audio file
python main_Interaction.py --audio 音频路径
```

### GraphRAG Management

**GraphRAG CLI Usage**:
```bash
# Show help
python main_graphrag_cli.py --help

# Interactive mode
python main_graphrag_cli.py

# Single query
python main_graphrag_cli.py --query "港口设备有哪些类型"

# View graph statistics
python main_graphrag_cli.py --stats

# Rebuild graph index
python main_graphrag_cli.py --rebuild

# Specify return count
python main_graphrag_cli.py --query "查询内容" --top-k 5
```

**GraphRAG Interactive Commands**:
- `查询 <问题>` - 执行图谱检索
- `stats` - 查看图谱统计
- `rebuild` - 重建图谱索引
- `status` - 查看系统状态
- `help` - 显示帮助信息
- `exit/quit` - 退出程序

**Check GraphRAG Availability**:
```python
from src.graph_rag import check_graph_rag_available, get_graph_rag_instance

if check_graph_rag_available():
    graph_rag = get_graph_rag_instance()
    # GraphRAG features are available
```

**Programmatic GraphRAG Usage**:
```python
from src.graph_rag import GraphRAGConfig, GraphRAGRetriever, get_graph_rag_instance

# Get GraphRAG instance (returns None if unavailable or not enabled)
graph_rag = get_graph_rag_instance()
if graph_rag:
    # Retrieve knowledge from graph
    results = graph_rag.retrieve("查询内容")
    for result in results:
        print(f"{result['score']:.3f}: {result['text']}")

    # Get graph statistics
    stats = graph_rag.get_graph_stats()
    print(f"Nodes: {stats['node_count']}, Relations: {stats['relation_count']}")

    # Get status
    status = graph_rag.get_status()

    # Rebuild graph index after adding documents
    graph_rag.rebuild_index()
```

### RAG Management

**Rebuild Knowledge Base Index**:
```bash
# In interactive mode
rag:rebuild

# Or using Python API
python -c "from src.rag import get_rag_instance; rag = get_rag_instance(); rag.rebuild_index()"
```

**Check RAG Dependencies Availability**:
```python
from src.rag import check_rag_available
if check_rag_available():
    # RAG features are available
    pass
```

**Programmatic RAG Usage**:
```python
from src.rag import get_rag_instance

# Get RAG instance (returns None if unavailable)
rag = get_rag_instance()
if rag:
    # Retrieve knowledge for a query
    results = rag.retrieve("查询内容")
    for result in results:
        print(f"{result['score']:.3f}: {result['text']}")

    # Format results for VLM prompt
    context = rag.format_context(results)

    # Get status
    status = rag.get_status()

    # Rebuild index after adding documents
    rag.rebuild_index()
```

### Interactive Commands
- Input text directly and press Enter
- Input file paths (images, audio, text files)
- Type `r` and press Enter for real-time audio recording (5 seconds)
- `rag:status` - View RAG module status
- `rag:enable` / `rag:disable` - Toggle RAG enhancement
- `rag:rebuild` - Rebuild knowledge base vector index (and GraphRAG if enabled)
- `rag:graph` - View GraphRAG statistics (when enabled)

## Architecture

### Core Data Flow
```
Input (Audio/Text/Image)
  ↓
ASR Module (if audio) → Transcribed Text
  ↓
Context Builder → Combines all inputs
  ↓
RAG Module (optional) → Retrieves relevant knowledge from vector DB
  ↓
VLM Module (Qwen2-VL) → Generates structured instruction (with RAG context)
  ↓
Parser Module → Extracts validated Pydantic model
  ↓
Structured Instruction Output
```

### Module Structure

**main_Interaction.py** - CLI orchestrator
- Entry point for all interactions
- Handles command-line arguments
- Manages interactive console loop
- Coordinates all modules
- Command dispatch pattern using `RAG_COMMAND_HANDLERS` dictionary for extensible command handling

**main_graphrag_cli.py** - GraphRAG CLI interface (NEW)
- Dedicated GraphRAG testing and management
- Interactive mode with commands: query, stats, rebuild, status
- Single query mode via `--query` argument
- Statistics viewing via `--stats` argument
- Index rebuilding via `--rebuild` argument

**main_rag_cli.py** - RAG CLI interface
- Traditional RAG testing and management
- Interactive mode for RAG queries
- Single query mode
- Statistics and status viewing

**src/asr.py** - Speech Recognition (Whisper)
- Factory pattern with LRU caching: `get_asr_instance()`
- Supports real-time recording (5s default) and file inputs
- Audio formats: WAV, MP3, M4A, FLAC, OGG
- Memory-optimized (no temp files)

**src/vlm.py** - Vision-Language Model (Qwen2-VL-2B)
- Factory pattern with LRU caching: `get_vlm_instance()`
- Processes multimodal inputs (text + images)
- Generates structured output with Pydantic models
- Robust error handling and logging

**src/parser.py** - Structured Data Parser
- Primary: LangChain-based structured parsing with Pydantic
- Fallback: Rule-based extraction using regex/keywords
- Validates and returns `Instruction` models

**src/config.py** - Configuration Management
- Singleton pattern for global settings
- Loads from `config.ini`
- Centralizes all tunable parameters

**src/utils.py** - Utilities
- Device selection (CPU/CUDA/Auto detection)
- Image processing and encoding
- Common helper functions

**src/rag.py** - RAG Knowledge Retrieval
- Factory pattern with LRU caching: `get_rag_instance()`
- BGE-M3 embedding model for multilingual support (2.3GB)
- SimpleVectorStore for vector storage (JSON-based, no file locking, preserves nodes for BM25)
- LlamaIndex integration with SimpleDirectoryReader for document loading
- GraphRAG integration using PropertyGraphIndex
- Hybrid retrieval with graph-based relationships
- Advanced features: hybrid retrieval (BM25 + vector), adaptive thresholding, reranking
- Simplified codebase (423 lines, -48% from original) using LlamaIndex native components

**src/graph_rag.py** - GraphRAG Core Module (REFACTORED)
- PropertyGraphIndex-based knowledge graph with complex relationship reasoning
- Dataclass-based configuration (`GraphRAGConfig`) for type safety
- Factory method: `GraphRAGConfig.from_config()` for loading from config.ini
- Follows LlamaIndex official documentation:
  - Uses `load_index_from_storage()` for loading
  - Uses `index.storage_context.persist()` for saving
  - Stores to `data/graph_db/storage/` directory
- Supports multiple extractors: ImplicitPathExtractor, DynamicLLMPathExtractor, SimpleLLMPathExtractor, SchemaLLMPathExtractor
- Hybrid extractors: ImplicitPathExtractor (fast) + DynamicLLMPathExtractor (accurate)
- Domain-specific entity hints: 港口设备, 系统机构, 备件零件, 规格型号, 存放库位
- Relation hints: 包含, 属于, 规格为, 存放于, 别名为
- Multi-hop retrieval with configurable path depth (default: 1 for performance)
- Query caching with TTL (3600s default) and size limit (100 entries)
- SimplePropertyGraphStore for graph storage (no Neo4j required)

**src/graph_extractors.py** - Custom Graph Extractors (REFACTORED)
- Factory pattern for creating knowledge graph extractors
- Supports 4 extractor types based on `extractor_type` config:
  - `implicit`: Only ImplicitPathExtractor (no LLM, fast)
  - `dynamic`: DynamicLLMPathExtractor (recommended, with entity type hints)
  - `simple`: SimpleLLMPathExtractor (basic)
  - `schema`: SchemaLLMPathExtractor (strict mode, higher accuracy)
- Domain-specific entity and relationship hints for port domain
- Parallel processing for efficient triple extraction
- Fallback strategies for LLM unavailability

### Key Design Patterns

**Singleton with LRU Caching**: ASR, VLM, RAG, and GraphRAG instances are cached to prevent re-initialization
```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_asr_instance():
    return ASR()

@lru_cache(maxsize=1)
def get_graph_rag_instance():
    config = GraphRAGConfig.from_config()
    rag = GraphRAGRetriever(config)
    return rag if rag.is_enabled() else None
```

**Factory Pattern**: Centralized model instantiation via `get_*_instance()` functions

**Dataclass Configuration**: GraphRAG uses `@dataclass` for type-safe configuration with factory method pattern
```python
@dataclass
class GraphRAGConfig:
    graph_enabled: bool
    graph_db_path: Path

    @classmethod
    def from_config(cls) -> "GraphRAGConfig":
        return cls(
            graph_enabled=settings.getboolean("rag", "graph_enabled", fallback=False),
            # ...
        )
```

**Fallback Strategy**: Parser gracefully degrades from structured parsing to rule-based extraction. RAG gracefully degrades if dependencies missing or initialization fails. GraphRAG gracefully falls back to traditional RAG when LLM unavailable.

**Configuration-Driven**: All model parameters, thresholds, and paths in `config.ini`

## Configuration

All settings are managed through `config.ini`:

```ini
[models]
asr_model = large-v3-turbo        # Whisper model variant
asr_device = auto                  # cpu/cuda/auto
asr_language = zh                  # Speech recognition language
vlm_model = Qwen/Qwen2-VL-2B-Instruct
vlm_device = auto
vlm_max_tokens = 512

[parser]
confidence_threshold = 0.9         # Minimum confidence for parsing
default_urgency = 中               # Default urgency level
fallback_part_name = 未知备件      # Default when parsing fails
fallback_description_prefix = 自动解析失败，原始信息

[paths]
cache_dir = ./models               # Model cache location
output_dir = ./output              # Output files location

[rag]
enabled = true                     # RAG feature toggle
graph_enabled = true               # GraphRAG feature toggle
embedding_model = BAAI/bge-m3      # Embedding model (2.3GB)
device = auto                      # cpu/cuda/auto
top_k = 3                          # Number of retrieved chunks
mode = hybrid                      # Retrieval mode: fixed/adaptive/hybrid

# ===== GraphRAG configuration (refactored) =====
[graph_rag]
# Graph building configuration
# extractor type: implicit, dynamic, simple, schema
# - implicit: Only implicit extractor (no LLM, fast)
# - dynamic: Dynamic LLM extractor (recommended, with entity type hints)
# - simple: Simple LLM extractor (basic)
# - schema: Schema LLM extractor (strict mode, higher accuracy)
extractor_type = dynamic
# maximum triplets per chunk
max_triplets_per_chunk = 15
# parallel workers
num_workers = 4
# Entity hints (comma-separated)
entity_hints = 港口设备, 系统机构, 备件零件, 规格型号, 存放库位
# Relation hints (comma-separated)
relation_hints = 包含, 属于, 规格为, 存放于, 别名为

# LLM configuration for graph extraction
# LLM provider: deepseek, openai, ollama
llm_provider = deepseek
deepseek_api_key = <your-api-key>
deepseek_base_url = https://api.deepseek.com/v1
deepseek_model = deepseek-chat
deepseek_temperature = 0.7

[graph_retrieval]
# Graph retrieval configuration
# sub retrievers: vector, synonym (comma-separated)
sub_retrievers = vector,synonym
vector_top_k = 5
# relation depth (1=direct, 2=indirect)
vector_path_depth = 1
synonym_max_keywords = 8
synonym_path_depth = 1

[graph_performance]
# Performance optimization
# query cache TTL (seconds, 0=disabled)
query_cache_ttl = 3600
# maximum cache entries
cache_max_size = 100

[rag.retrieval]
mode = hybrid                      # fixed, adaptive, or hybrid
threshold_strict = 0.7             # Strict threshold for adaptive mode
threshold_medium = 0.35            # Medium threshold (tuned for better recall)
threshold_relaxed = 0.25            # Relaxed threshold
min_results_expected = 2           # Minimum results for adaptive mode
hybrid_enabled = true              # Enable hybrid retrieval (BM25 + vector)
fusion_method = rrf                # Fusion: rrf/weighted/concat
vector_weight = 0.7                # Weight for vector in weighted fusion
keyword_weight = 0.3               # Weight for BM25 in weighted fusion

[rag.rerank]
enabled = true                     # Enable reranking
model = BAAI/bge-reranker-v2-m3    # Reranker model
rerank_top_k = 10                  # Number of candidates to rerank
final_top_k = 3                    # Final number of results after reranking
device = auto                      # cpu/cuda/auto

[rag.chunking]
# Chunking strategy for NON-Markdown files: semantic or fixed
strategy = semantic                # semantic or fixed

# Fixed chunking parameters
chunk_size = 1024                  # For fixed strategy
chunk_overlap = 128                # Overlap for fixed strategy

# Semantic chunking parameters
semantic_splitter_threshold = 0.6  # Threshold for semantic splitting
min_chunk_size = 128               # Minimum chunk size

# Markdown chunking parameters (for .md files)
# When enabled, .md files use Markdown-specific chunking regardless of strategy setting
# Other files still follow the strategy setting above
markdown_chunking_enabled = true   # Enable markdown-specific chunking for .md files
markdown_heading_level = 2         # Split by X-level heading (1=#, 2=##, 3=###)
markdown_preserve_tables = true    # Keep tables intact (no splitting)
metadata_include_heading = true    # Include heading info in metadata
metadata_include_position = false  # Include original position in metadata

[paths.knowledge]
knowledge_base = ./data/knowledge_base  # Knowledge base documents
vector_db = ./data/vector_db           # SimpleVectorStore (JSON-based, no file locking)
graph_db = ./data/graph_db             # Graph storage path
```

## Important Implementation Details

### Memory Optimization
- Audio data is processed in-memory using numpy arrays (no temporary files)
- Images are encoded as base64 when passed to VLM
- Model instances are cached to avoid reloading
- **NEW**: GraphRAG query caching reduces redundant LLM calls
- **NEW**: GraphRAG uses dataclass for efficient configuration management

### Error Handling
- Comprehensive try-catch blocks throughout all modules
- VLM failures trigger fallback parsing
- RAG initialization failures are logged but don't crash the system
- **NEW**: GraphRAG gracefully falls back to traditional RAG when LLM unavailable
- User-friendly error messages in CLI
- System continues gracefully even when individual components fail

### Device Selection
- Automatic CUDA detection when available
- Manual override via config.ini (cpu/cuda/auto)
- Model loading uses appropriate `torch_dtype` based on device
- **NEW**: GraphRAG supports separate device configuration for embedding and LLM

### Audio Recording
- Interactive mode: Press `r` for 5-second real-time recording
- Live countdown during recording
- Direct numpy array processing (sounddevice library)

### File Type Detection
- Automatic detection based on file extension
- Images: JPG, PNG, BMP, WebP → VLM analysis
- Audio: WAV, MP3, M4A, FLAC, OGG → ASR transcription
- Text files (.txt) → Direct content reading

### RAG Knowledge Base
- Knowledge base documents stored in `data/knowledge_base/`
- Supported formats: `.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.pdf`, `.docx`, `.doc`, `.xlsx`, `.xls`
- Documents are chunked and embedded using BGE-M3
- Vector storage in `data/vector_db/vector_store.json` using SimpleVectorStore (JSON-based, no file locking)
- **NEW**: Graph storage in `data/graph_db/storage/` using SimplePropertyGraphStore (follows LlamaIndex official pattern)
- Retrieved context is automatically injected into VLM system prompt
- RAG can be toggled dynamically at runtime via `rag:enable`/`rag:disable`
- **NEW**: GraphRAG can be toggled via `graph_enabled` in config
- Document loading uses LlamaIndex's SimpleDirectoryReader with built-in multi-format support

### GraphRAG Implementation (REFACTORED)
The GraphRAG system extends traditional vector retrieval with knowledge graphs, following LlamaIndex official best practices:

**Graph Construction**:
- Uses PropertyGraphIndex with SimplePropertyGraphStore (no Neo4j required)
- Dataclass-based configuration for type safety and maintainability
- Factory method pattern: `GraphRAGConfig.from_config()`
- Follows LlamaIndex official API:
  - Index loading: `load_index_from_storage(storage_context)`
  - Index saving: `index.storage_context.persist(persist_dir=str(storage_dir))`
  - Storage location: `data/graph_db/storage/` (not `graph_store.json`)
- **NEW**: Supports 4 extractor types:
  - `ImplicitPathExtractor`: No LLM required, fast baseline relationships
  - `DynamicLLMPathExtractor`: LLM with entity/relation type hints (recommended)
  - `SimpleLLMPathExtractor`: Basic LLM extraction
  - `SchemaLLMPathExtractor`: Strict schema validation (highest accuracy)
- Domain-specific entity hints: 港口设备, 系统机构, 备件零件, 规格型号, 存放库位
- Relation hints: 包含, 属于, 规格为, 存放于, 别名为

**Graph Retrieval**:
- Multi-hop retrieval with configurable path depth (default: 1 for performance)
- Hybrid sub-retrievers: VectorContextRetriever + LLMSynonymRetriever
- Query caching with TTL (3600s default) and size limit (100 entries)
- Results automatically annotated with source type ([图谱检索])

**Performance Optimizations**:
- Query cache reduces redundant graph traversals
- Parallel processing for entity extraction
- Lightweight ImplicitPathExtractor for fast baseline relationships
- Configurable limits for LLM calls to control latency
- Dataclass configuration reduces memory overhead

### RAG Retrieval Modes
The RAG module supports three retrieval modes configured via `[rag.retrieval] mode`:

**Fixed Mode**: Simple vector retrieval with fixed similarity threshold
- Uses `threshold_medium` for all queries
- Predictable performance, no adaptive behavior

**Adaptive Mode**: Three-tier fallback threshold system
- Tries `threshold_medium` → `threshold_strict` → `threshold_relaxed`
- Returns results when `min_results_expected` is met with average score ≥ 0.4
- Useful when query quality varies significantly

**Hybrid Mode**: Combines BM25 keyword search with vector retrieval
- Both retrievers return `top_k * 2` candidates
- Results fused using RRF (Reciprocal Rank Fusion) by default
- Optional fusion methods: `weighted` (custom weights) or `concat` (simple merge)
- Best for comprehensive search across semantic and lexical matches

All modes support optional reranking using BGE-reranker-v2-m3 for final result refinement.

### RAG Chunking Strategies
The RAG module supports flexible chunking strategies configured via `[rag.chunking]`:

**Base Strategy (for non-Markdown files)**:
- `strategy = semantic` (Recommended): Uses semantic similarity for splitting
- `strategy = fixed`: Simple character-based chunking with fixed size

**Markdown Chunking (independent switch)**:
- `markdown_chunking_enabled = true`: Enables specialized Markdown chunking for `.md` files only
- When enabled, `.md` files are split by heading levels (e.g., `##` for H2)
- Other files (PDF, DOCX, TXT, etc.) automatically use the base `strategy` setting
- Preserves table integrity (tables are never split)
- Metadata includes heading hierarchy for better context

**Configuration Examples**:

```ini
# Example 1: Semantic for all files
[rag.chunking]
strategy = semantic
markdown_chunking_enabled = false

# Example 2: Semantic for non-MD, Markdown for .md files (RECOMMENDED)
[rag.chunking]
strategy = semantic
markdown_chunking_enabled = true
markdown_heading_level = 2

# Example 3: Fixed for non-MD, Markdown for .md files
[rag.chunking]
strategy = fixed
chunk_size = 1024
markdown_chunking_enabled = true
```

**Configuration Tips**:
- Set `markdown_heading_level=2` to split by `##` (section-level) headings
- Set `markdown_heading_level=1` to split by `#` (document-level) headings
- Keep `markdown_preserve_tables=true` to ensure tables remain intact
- For technical manuals, enable `markdown_chunking_enabled` for better chapter-level retrieval

### GraphRAG Configuration
GraphRAG introduces new configuration sections for advanced features:

```ini
# Enable GraphRAG alongside traditional RAG
[rag]
graph_enabled = true

# Graph retrieval settings
[graph_rag]
# Extractor type (refactored)
extractor_type = dynamic  # implicit, dynamic, simple, or schema

# Graph retrieval
[graph_retrieval]
sub_retrievers = vector,synonym  # Active sub-retrievers
vector_path_depth = 1           # Multi-hop depth (1=direct only)
synonym_max_keywords = 8         # Max keywords for synonym expansion

# Performance tuning
[graph_performance]
query_cache_ttl = 3600           # Cache expiration (seconds)
cache_max_size = 100            # Maximum cached results
```

**GraphRAG Performance Considerations**:
- First build takes 20-60s for typical document sets
- Subsequent queries are faster with caching
- Multi-hop retrieval (path_depth > 1) increases latency but improves complex queries
- Entity extraction works best with OpenAI API, but falls back gracefully
- Dataclass configuration reduces initialization overhead

## Pydantic Data Models

The system uses structured output models defined in `src/parser.py`:

- **PortInstruction**: Main parsed instruction container with fields:
  - `part_name`: Part/Equipment name
  - `quantity`: Required quantity
  - `urgency`: Urgency level (低/中/高)
  - `location`: Location description
  - `description`: Detailed description
  - `action_required`: Required action (更换/维修/检查)
  - `confidence`: Confidence score (0-1)

All VLM outputs are parsed into these Pydantic models for type safety and validation.

## Additional Documentation

For detailed information about RAG module implementation, including:
- Complete architecture and data flow diagrams
- Problem-solving history (ChromaDB file locking, BM25 compatibility, version conflicts)
- Performance metrics and optimization guidelines
- Best practices and FAQ

See: `RAG模块技术文档.md` (RAG Module Technical Documentation)
