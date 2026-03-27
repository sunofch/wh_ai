# src/ 目录重组设计文档

**日期**: 2026-03-27
**目标**: 改善代码可维护性和入口点清晰度，按技术栈分组组织 src/ 目录

## 背景

当前 `src/` 目录采用扁平结构，包含 14 个文件（13 个模块 + 1 个 __init__.py）。随着项目发展，这种结构导致：
- 模块职责边界不清晰
- 新功能添加时缺乏明确的文件放置位置
- 相关模块分散，难以理解和维护

## 设计目标

1. **更好的可维护性**: 相关模块集中管理，职责清晰
2. **清晰的入口点**: 目录结构自解释，易于导航

## 新目录结构

```
src/
├── rag/                           # RAG 检索系统
│   ├── __init__.py
│   ├── traditional.py             # 原 rag.py
│   ├── graph.py                   # 原 graph_rag.py
│   ├── manager.py                 # 原 rag_manager.py
│   └── graph_extractors.py        # 原 graph_extractors.py
├── vlm/                           # VLM 推理引擎
│   ├── __init__.py
│   ├── router.py                  # 原 vlm.py
│   ├── qwen2.py                   # 原 qwen2vlm.py
│   ├── qwen35.py                  # 原 qwen35vlm.py
│   └── server.py                  # 原 vlm_server.py
├── asr/                           # ASR 语音识别
│   ├── __init__.py
│   └── whisper.py                 # 原 asr.py
├── parser/                        # 指令解析器
│   ├── __init__.py
│   └── parser.py                  # 原 parser.py
├── common/                        # 通用模块
│   ├── __init__.py
│   ├── config.py
│   ├── utils.py
│   └── reranker.py
└── __init__.py
```

## 模块映射表

| 原文件名 | 新路径 | 新文件名 |
|---------|--------|---------|
| `rag.py` | `src/rag/` | `traditional.py` |
| `graph_rag.py` | `src/rag/` | `graph.py` |
| `rag_manager.py` | `src/rag/` | `manager.py` |
| `graph_extractors.py` | `src/rag/` | `graph_extractors.py` |
| `vlm.py` | `src/vlm/` | `router.py` |
| `qwen2vlm.py` | `src/vlm/` | `qwen2.py` |
| `qwen35vlm.py` | `src/vlm/` | `qwen35.py` |
| `vlm_server.py` | `src/vlm/` | `server.py` |
| `asr.py` | `src/asr/` | `whisper.py` |
| `parser.py` | `src/parser/` | `parser.py` |
| `config.py` | `src/common/` | `config.py` |
| `utils.py` | `src/common/` | `utils.py` |
| `reranker.py` | `src/common/` | `reranker.py` |
| `__init__.py` | `src/` | 保持（更新导入路径） |

## 导入路径变更

### 内部导入（模块之间）

**变更前**:
```python
from src.rag import RAGRetriever
from src.vlm import get_vlm_instance
from src.asr import WhisperASR
from src.config import settings
from src.utils import get_device
```

**变更后**:
```python
from src.rag.traditional import RAGRetriever
from src.vlm.router import get_vlm_instance
from src.asr.whisper import WhisperASR
from src.common.config import settings
from src.common.utils import get_device
```

### 便捷导入（通过 __init__.py）

每个子模块的 `__init__.py` 提供便捷导出：

**src/rag/__init__.py**:
```python
from .traditional import RAGRetriever, get_rag_instance, check_rag_available
from .graph import GraphRAGRetriever, get_graph_rag_instance, check_graph_rag_available
from .manager import UnifiedRAGManager, initialize_rag_system, get_unified_rag_manager

__all__ = [
    'RAGRetriever', 'get_rag_instance', 'check_rag_available',
    'GraphRAGRetriever', 'get_graph_rag_instance', 'check_graph_rag_available',
    'UnifiedRAGManager', 'initialize_rag_system', 'get_unified_rag_manager'
]
```

**src/vlm/__init__.py**:
```python
from .router import get_vlm_instance, VLM_NAME
from .server import get_vlm_server_manager

__all__ = ['get_vlm_instance', 'VLM_NAME', 'get_vlm_server_manager']
```

**src/asr/__init__.py**:
```python
from .whisper import WhisperASR, get_asr_instance

__all__ = ['WhisperASR', 'get_asr_instance']
```

**src/parser/__init__.py**:
```python
from .parser import PortInstructionParser, parse_port_instruction

__all__ = ['PortInstructionParser', 'parse_port_instruction']
```

**src/common/__init__.py**:
```python
from .config import settings
from .utils import get_device
from .reranker import get_reranker_instance

__all__ = ['settings', 'get_device', 'get_reranker_instance']
```

### 外部代码可选导入方式

```python
# 方式 1: 详细导入（推荐，语义明确）
from src.rag.traditional import RAGRetriever
from src.vlm.router import get_vlm_instance

# 方式 2: 便捷导入（向后兼容）
from src.rag import RAGRetriever
from src.vlm import get_vlm_instance
```

## 受影响的文件

需要更新导入语句的文件：

1. **入口文件**:
   - `main_interaction.py`
   - `main_rag.py`
   - `main_warehouse.py`

2. **测试文件**:
   - `tests/test_reranker.py`
   - `tests/test_graph_rag_reranker.py`
   - `test_rag_context.py`
   - `test_warehouse_system.py`

3. **模块内部**（相互引用）:
   - `src/rag/manager.py` (引用 traditional, graph)
   - `src/vlm/router.py` (引用 qwen2, qwen35)
   - `src/vlm/server.py` (引用 config)

## 内部依赖映射

完整的模块间导入路径更新表：

| 原导入语句 | 新导入语句 | 影响的文件 |
|-----------|-----------|-----------|
| `from src.reranker import ...` | `from src.common.reranker import ...` | src/rag/graph.py, src/rag/traditional.py |
| `from src.graph_extractors import ...` | `from .graph_extractors import ...` | src/rag/graph.py |
| `from src.vlm_server import ...` | `from .server import ...` | src/vlm/qwen2.py, src/vlm/qwen35.py |
| `from src.config import ...` | `from src.common.config import ...` | 所有模块 |
| `from src.utils import ...` | `from src.common.utils import ...` | 所有模块 |
| `from src.vlm import ...` | `from .router import ...` | src/vlm/qwen2.py, src/vlm/qwen35.py |

## 迁移步骤

1. **创建新目录结构**
   ```bash
   mkdir -p src/rag src/vlm src/asr src/parser src/common
   ```

2. **移动并重命名文件**
   - 使用 git mv 保留历史记录
   - 按映射表移动文件

3. **更新模块内部导入**
   - 更新各文件内部的 `from src.xxx import` 语句

4. **创建 __init__.py 文件**
   - 为每个子模块创建便捷导出

5. **更新外部导入**
   - 更新 main_xxx.py 文件
   - 更新 tests/ 目录

6. **验证导入路径**
   ```bash
   # 验证所有模块可以正确导入
   python -c "from src.rag import *; from src.vlm import *; from src.asr import *; from src.parser import *; from src.common import *"
   python -c "import main_interaction; import main_rag"
   ```

7. **运行测试验证**
   - 运行所有测试确保功能正常
   - 手动测试各入口点

8. **回滚计划**（如测试失败）
   ```bash
   # 如果验证失败，立即回滚所有更改
   git checkout HEAD -- src/
   ```

9. **更新文档**
   - 更新 CLAUDE.md 中的模块结构说明
   - 更新导入示例代码

## 风险与缓解

| 风险 | 缓解措施 |
|-----|---------|
| 导入路径遗漏导致运行时错误 | 使用 IDE 全局搜索替换 + 人工审核 |
| 测试覆盖不全 | 运行完整测试套件验证 |
| 向后兼容性问题 | 通过 `__init__.py` 提供便捷导入 |

## 设计原则

1. **单一职责**: 每个目录对应一个技术栈领域
2. **清晰命名**: 文件名自解释，不需要注释
3. **易于扩展**: 新增模型或检索方式时，目录结构自然引导位置
4. **向后兼容**: 通过 `__init__.py` 减少外部代码改动

## 范围说明

本次重组仅涉及 `src/` 目录，不包括 `services/` 目录（仓库调度系统）。两者是独立运行的业务系统，暂时保持分离。
