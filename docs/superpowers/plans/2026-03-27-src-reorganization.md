# src/ 目录重组实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 src/ 目录从扁平结构重组为按技术栈分组的层级结构，提高代码可维护性和导航清晰度

**架构:** 按技术领域分为 5 个子目录：rag/（检索）、vlm/（推理）、asr/（语音）、parser/（解析）、common/（通用），每个子目录通过 __init__.py 提供便捷导出以保持向后兼容

**技术栈:** Python 3.x, Git（用于保留文件历史）

---

## 文件结构映射

### 创建的新文件
- `src/rag/__init__.py` - RAG 模块便捷导出
- `src/vlm/__init__.py` - VLM 模块便捷导出
- `src/asr/__init__.py` - ASR 模块便捷导出
- `src/parser/__init__.py` - Parser 模块便捷导出
- `src/common/__init__.py` - Common 模块便捷导出

### 移动的文件（使用 git mv 保留历史）
| 原路径 | 新路径 |
|-------|--------|
| `src/rag.py` | `src/rag/traditional.py` |
| `src/graph_rag.py` | `src/rag/graph.py` |
| `src/rag_manager.py` | `src/rag/manager.py` |
| `src/graph_extractors.py` | `src/rag/graph_extractors.py` |
| `src/vlm.py` | `src/vlm/router.py` |
| `src/qwen2vlm.py` | `src/vlm/qwen2.py` |
| `src/qwen35vlm.py` | `src/vlm/qwen35.py` |
| `src/vlm_server.py` | `src/vlm/server.py` |
| `src/asr.py` | `src/asr/whisper.py` |
| `src/parser.py` | `src/parser/parser.py` |
| `src/config.py` | `src/common/config.py` |
| `src/utils.py` | `src/common/utils.py` |
| `src/reranker.py` | `src/common/reranker.py` |

### 需要更新导入的文件
- `src/__init__.py` - 根模块初始化
- `src/rag/traditional.py` - 内部导入
- `src/rag/graph.py` - 内部导入
- `src/rag/manager.py` - 内部导入
- `src/vlm/router.py` - 内部导入
- `src/vlm/qwen2.py` - 内部导入
- `src/vlm/qwen35.py` - 内部导入
- `src/vlm/server.py` - 内部导入
- `src/asr/whisper.py` - 内部导入
- `main_interaction.py` - 外部导入
- `main_rag.py` - 外部导入
- `start_vlm_server.py` - 外部导入
- `status_vlm_server.py` - 外部导入
- `stop_vlm_server.py` - 外部导入
- `tests/test_reranker.py` - 测试导入
- `tests/test_graph_rag_reranker.py` - 测试导入
- `test_rag_context.py` - 测试导入

---

## Task 1: 创建新目录结构

**Files:**
- Create: `src/rag/`, `src/vlm/`, `src/asr/`, `src/parser/`, `src/common/`

- [ ] **Step 1: 创建所有子目录**

```bash
mkdir -p src/rag src/vlm src/asr src/parser src/common
```

- [ ] **Step 2: 验证目录创建成功**

```bash
ls -la src/ | grep -E "rag|vlm|asr|parser|common"
```

Expected output: 显示 5 个新创建的目录

- [ ] **Step 3: 提交**

```bash
git add src/
git commit -m "refactor: 创建 src/ 子目录结构

- 创建 rag/, vlm/, asr/, parser/, common/ 子目录
- 为后续模块重组做准备

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 移动 RAG 相关文件

**Files:**
- Move: `src/rag.py` → `src/rag/traditional.py`
- Move: `src/graph_rag.py` → `src/rag/graph.py`
- Move: `src/rag_manager.py` → `src/rag/manager.py`
- Move: `src/graph_extractors.py` → `src/rag/graph_extractors.py`

- [ ] **Step 1: 移动 rag.py**

```bash
git mv src/rag.py src/rag/traditional.py
```

- [ ] **Step 2: 移动 graph_rag.py**

```bash
git mv src/graph_rag.py src/rag/graph.py
```

- [ ] **Step 3: 移动 rag_manager.py**

```bash
git mv src/rag_manager.py src/rag/manager.py
```

- [ ] **Step 4: 移动 graph_extractors.py**

```bash
git mv src/graph_extractors.py src/rag/graph_extractors.py
```

- [ ] **Step 5: 验证文件移动成功**

```bash
ls -la src/rag/
```

Expected output: 显示 4 个文件（traditional.py, graph.py, manager.py, graph_extractors.py）

- [ ] **Step 6: 提交**

```bash
git add src/
git commit -m "refactor(rag): 移动 RAG 模块到 src/rag/ 子目录

- rag.py → src/rag/traditional.py
- graph_rag.py → src/rag/graph.py
- rag_manager.py → src/rag/manager.py
- graph_extractors.py → src/rag/graph_extractors.py

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 移动 VLM 相关文件

**Files:**
- Move: `src/vlm.py` → `src/vlm/router.py`
- Move: `src/qwen2vlm.py` → `src/vlm/qwen2.py`
- Move: `src/qwen35vlm.py` → `src/vlm/qwen35.py`
- Move: `src/vlm_server.py` → `src/vlm/server.py`

- [ ] **Step 1: 移动 vlm.py**

```bash
git mv src/vlm.py src/vlm/router.py
```

- [ ] **Step 2: 移动 qwen2vlm.py**

```bash
git mv src/qwen2vlm.py src/vlm/qwen2.py
```

- [ ] **Step 3: 移动 qwen35vlm.py**

```bash
git mv src/qwen35vlm.py src/vlm/qwen35.py
```

- [ ] **Step 4: 移动 vlm_server.py**

```bash
git mv src/vlm_server.py src/vlm/server.py
```

- [ ] **Step 5: 验证文件移动成功**

```bash
ls -la src/vlm/
```

Expected output: 显示 4 个文件（router.py, qwen2.py, qwen35.py, server.py）

- [ ] **Step 6: 提交**

```bash
git add src/
git commit -m "refactor(vlm): 移动 VLM 模块到 src/vlm/ 子目录

- vlm.py → src/vlm/router.py
- qwen2vlm.py → src/vlm/qwen2.py
- qwen35vlm.py → src/vlm/qwen35.py
- vlm_server.py → src/vlm/server.py

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 移动 ASR 和 Parser 文件

**Files:**
- Move: `src/asr.py` → `src/asr/whisper.py`
- Move: `src/parser.py` → `src/parser/parser.py`

- [ ] **Step 1: 移动 asr.py**

```bash
git mv src/asr.py src/asr/whisper.py
```

- [ ] **Step 2: 移动 parser.py**

```bash
git mv src/parser.py src/parser/parser.py
```

- [ ] **Step 3: 验证文件移动成功**

```bash
ls -la src/asr/ src/parser/
```

Expected output: asr/ 显示 whisper.py，parser/ 显示 parser.py

- [ ] **Step 4: 提交**

```bash
git add src/
git commit -m "refactor: 移动 ASR 和 Parser 模块到子目录

- asr.py → src/asr/whisper.py
- parser.py → src/parser/parser.py

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: 移动 Common 模块文件

**Files:**
- Move: `src/config.py` → `src/common/config.py`
- Move: `src/utils.py` → `src/common/utils.py`
- Move: `src/reranker.py` → `src/common/reranker.py`

- [ ] **Step 1: 移动 config.py**

```bash
git mv src/config.py src/common/config.py
```

- [ ] **Step 2: 移动 utils.py**

```bash
git mv src/utils.py src/common/utils.py
```

- [ ] **Step 3: 移动 reranker.py**

```bash
git mv src/reranker.py src/common/reranker.py
```

- [ ] **Step 4: 验证文件移动成功**

```bash
ls -la src/common/
```

Expected output: 显示 3 个文件（config.py, utils.py, reranker.py）

- [ ] **Step 5: 提交**

```bash
git add src/
git commit -m "refactor(common): 移动通用模块到 src/common/ 子目录

- config.py → src/common/config.py
- utils.py → src/common/utils.py
- reranker.py → src/common/reranker.py

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 创建 RAG 模块的 __init__.py

**Files:**
- Create: `src/rag/__init__.py`

- [ ] **Step 1: 创建 src/rag/__init__.py**

```python
"""RAG (Retrieval-Augmented Generation) 检索系统模块"""

# Traditional RAG (向量 + BM25)
from .traditional import (
    RAGRetriever,
    get_rag_instance,
    check_rag_available,
)

# GraphRAG (知识图谱)
from .graph import (
    GraphRAGRetriever,
    get_graph_rag_instance,
    check_graph_rag_available,
)

# Unified RAG Manager
from .manager import (
    UnifiedRAGManager,
    initialize_rag_system,
    get_unified_rag_manager,
)

__all__ = [
    # Traditional RAG
    'RAGRetriever',
    'get_rag_instance',
    'check_rag_available',
    # GraphRAG
    'GraphRAGRetriever',
    'get_graph_rag_instance',
    'check_graph_rag_available',
    # Manager
    'UnifiedRAGManager',
    'initialize_rag_system',
    'get_unified_rag_manager',
]
```

- [ ] **Step 2: 验证 Python 语法正确**

```bash
python -m py_compile src/rag/__init__.py
```

Expected: 无错误输出

- [ ] **Step 3: 提交**

```bash
git add src/rag/__init__.py
git commit -m "refactor(rag): 创建 RAG 模块便捷导出

- 通过 __init__.py 提供统一导入接口
- 支持传统 RAG 和 GraphRAG 的便捷访问

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: 创建 VLM 模块的 __init__.py

**Files:**
- Create: `src/vlm/__init__.py`

- [ ] **Step 1: 创建 src/vlm/__init__.py**

```python
"""VLM (Vision Language Model) 视觉语言模型推理引擎模块"""

from .router import get_vlm_instance, VLM_NAME
from .server import get_vlm_server_manager

__all__ = [
    'get_vlm_instance',
    'VLM_NAME',
    'get_vlm_server_manager',
]
```

- [ ] **Step 2: 验证 Python 语法正确**

```bash
python -m py_compile src/vlm/__init__.py
```

Expected: 无错误输出

- [ ] **Step 3: 提交**

```bash
git add src/vlm/__init__.py
git commit -m "refactor(vlm): 创建 VLM 模块便捷导出

- 提供 get_vlm_instance 和 VLM_NAME 的统一访问
- 集成 vLLM 服务器管理器

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: 创建 ASR 模块的 __init__.py

**Files:**
- Create: `src/asr/__init__.py`

- [ ] **Step 1: 创建 src/asr/__init__.py**

```python
"""ASR (Automatic Speech Recognition) 自动语音识别模块"""

from .whisper import WhisperASR, get_asr_instance

__all__ = [
    'WhisperASR',
    'get_asr_instance',
]
```

- [ ] **Step 2: 验证 Python 语法正确**

```bash
python -m py_compile src/asr/__init__.py
```

Expected: 无错误输出

- [ ] **Step 3: 提交**

```bash
git add src/asr/__init__.py
git commit -m "refactor(asr): 创建 ASR 模块便捷导出

- 提供 Whisper ASR 的统一访问接口

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 9: 创建 Parser 模块的 __init__.py

**Files:**
- Create: `src/parser/__init__.py`

- [ ] **Step 1: 创建 src/parser/__init__.py**

```python
"""Parser 指令解析器模块"""

from .parser import PortInstructionParser, parse_port_instruction

__all__ = [
    'PortInstructionParser',
    'parse_port_instruction',
]
```

- [ ] **Step 2: 验证 Python 语法正确**

```bash
python -m py_compile src/parser/__init__.py
```

Expected: 无错误输出

- [ ] **Step 3: 提交**

```bash
git add src/parser/__init__.py
git commit -m "refactor(parser): 创建 Parser 模块便捷导出

- 提供港口指令解析器的统一访问接口

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 10: 创建 Common 模块的 __init__.py

**Files:**
- Create: `src/common/__init__.py`

- [ ] **Step 1: 创建 src/common/__init__.py**

```python
"""Common 通用工具模块"""

from .config import settings
from .utils import get_device
from .reranker import get_reranker_instance

__all__ = [
    'settings',
    'get_device',
    'get_reranker_instance',
]
```

- [ ] **Step 2: 验证 Python 语法正确**

```bash
python -m py_compile src/common/__init__.py
```

Expected: 无错误输出

- [ ] **Step 3: 提交**

```bash
git add src/common/__init__.py
git commit -m "refactor(common): 创建 Common 模块便捷导出

- 提供配置、工具函数和 Reranker 的统一访问

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 11: 更新 src/rag/traditional.py 的导入

**Files:**
- Modify: `src/rag/traditional.py`

- [ ] **Step 1: 读取文件内容查看当前导入**

```bash
head -50 src/rag/traditional.py | grep -E "^from src\.|^import src\."
```

- [ ] **Step 2: 更新导入语句**

使用编辑器将以下导入：
```python
from src.reranker import get_reranker_instance
from src.config import settings
from src.utils import get_device
```

替换为：
```python
from src.common.reranker import get_reranker_instance
from src.common.config import settings
from src.common.utils import get_device
```

- [ ] **Step 3: 验证 Python 语法正确**

```bash
python -m py_compile src/rag/traditional.py
```

Expected: 无错误输出

- [ ] **Step 4: 提交**

```bash
git add src/rag/traditional.py
git commit -m "refactor(rag): 更新 traditional.py 的导入路径

- from src.reranker → from src.common.reranker
- from src.config → from src.common.config
- from src.utils → from src.common.utils

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 12: 更新 src/rag/graph.py 的导入

**Files:**
- Modify: `src/rag/graph.py`

- [ ] **Step 1: 读取文件内容查看当前导入**

```bash
head -50 src/rag/graph.py | grep -E "^from src\.|^import src\."
```

- [ ] **Step 2: 更新导入语句**

使用编辑器将以下导入：
```python
from src.config import settings
from src.utils import get_device
from src.reranker import get_reranker_instance
from src.graph_extractors import create_kg_extractors
```

替换为：
```python
from src.common.config import settings
from src.common.utils import get_device
from src.common.reranker import get_reranker_instance
from .graph_extractors import create_kg_extractors
```

- [ ] **Step 3: 验证 Python 语法正确**

```bash
python -m py_compile src/rag/graph.py
```

Expected: 无错误输出

- [ ] **Step 4: 提交**

```bash
git add src/rag/graph.py
git commit -m "refactor(rag): 更新 graph.py 的导入路径

- 更新 common 模块导入
- graph_extractors 改为相对导入

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 13: 更新 src/rag/manager.py 的导入

**Files:**
- Modify: `src/rag/manager.py`

- [ ] **Step 1: 读取文件内容查看当前导入**

```bash
head -50 src/rag/manager.py | grep -E "^from src\.|^import src\."
```

- [ ] **Step 2: 更新导入语句**

使用编辑器将以下导入：
```python
from src.rag import RAGRetriever
from src.graph_rag import GraphRAGRetriever
from src.config import settings
```

替换为：
```python
from .traditional import RAGRetriever
from .graph import GraphRAGRetriever
from src.common.config import settings
```

- [ ] **Step 3: 验证 Python 语法正确**

```bash
python -m py_compile src/rag/manager.py
```

Expected: 无错误输出

- [ ] **Step 4: 提交**

```bash
git add src/rag/manager.py
git commit -m "refactor(rag): 更新 manager.py 的导入路径

- RAG 模块改为相对导入
- config 改为 common 模块导入

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 14: 更新 src/vlm/router.py 的导入

**Files:**
- Modify: `src/vlm/router.py`

- [ ] **Step 1: 读取文件内容查看当前导入**

```bash
head -50 src/vlm/router.py | grep -E "^from src\.|^import src\."
```

- [ ] **Step 2: 更新导入语句**

使用编辑器将以下导入：
```python
from src.qwen2vlm import Qwen2VLM
from src.qwen35vlm import Qwen35VLM
from src.config import settings
```

替换为：
```python
from .qwen2 import Qwen2VLM
from .qwen35 import Qwen35VLM
from src.common.config import settings
```

- [ ] **Step 3: 验证 Python 语法正确**

```bash
python -m py_compile src/vlm/router.py
```

Expected: 无错误输出

- [ ] **Step 4: 提交**

```bash
git add src/vlm/router.py
git commit -m "refactor(vlm): 更新 router.py 的导入路径

- VLM 类改为相对导入
- config 改为 common 模块导入

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 15: 更新 src/vlm/qwen2.py 和 qwen35.py 的导入

**Files:**
- Modify: `src/vlm/qwen2.py`
- Modify: `src/vlm/qwen35.py`

- [ ] **Step 1: 更新 qwen2.py 的导入**

使用编辑器将以下导入：
```python
from src.vlm import get_vlm_server_manager
from src.config import settings
```

替换为：
```python
from .server import get_vlm_server_manager
from src.common.config import settings
```

- [ ] **Step 2: 更新 qwen35.py 的导入**

使用编辑器将以下导入：
```python
from src.vlm import get_vlm_server_manager
from src.config import settings
```

替换为：
```python
from .server import get_vlm_server_manager
from src.common.config import settings
```

- [ ] **Step 3: 验证 Python 语法正确**

```bash
python -m py_compile src/vlm/qwen2.py src/vlm/qwen35.py
```

Expected: 无错误输出

- [ ] **Step 4: 提交**

```bash
git add src/vlm/qwen2.py src/vlm/qwen35.py
git commit -m "refactor(vlm): 更新 qwen2/qwen35 的导入路径

- vlm_server 改为相对导入
- config 改为 common 模块导入

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 16: 更新 src/vlm/server.py 的导入

**Files:**
- Modify: `src/vlm/server.py`

- [ ] **Step 1: 读取文件内容查看当前导入**

```bash
head -50 src/vlm/server.py | grep -E "^from src\.|^import src\."
```

- [ ] **Step 2: 更新导入语句**

使用编辑器将以下导入：
```python
from src.config import settings
from src.utils import get_device
```

替换为：
```python
from src.common.config import settings
from src.common.utils import get_device
```

- [ ] **Step 3: 验证 Python 语法正确**

```bash
python -m py_compile src/vlm/server.py
```

Expected: 无错误输出

- [ ] **Step 4: 提交**

```bash
git add src/vlm/server.py
git commit -m "refactor(vlm): 更新 server.py 的导入路径

- config 和 utils 改为 common 模块导入

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 17: 更新 src/asr/whisper.py 的导入

**Files:**
- Modify: `src/asr/whisper.py`

- [ ] **Step 1: 读取文件内容查看当前导入**

```bash
head -50 src/asr/whisper.py | grep -E "^from src\.|^import src\."
```

- [ ] **Step 2: 更新导入语句**

使用编辑器将以下导入：
```python
from src.config import settings
from src.utils import get_device
```

替换为：
```python
from src.common.config import settings
from src.common.utils import get_device
```

- [ ] **Step 3: 验证 Python 语法正确**

```bash
python -m py_compile src/asr/whisper.py
```

Expected: 无错误输出

- [ ] **Step 4: 提交**

```bash
git add src/asr/whisper.py
git commit -m "refactor(asr): 更新 whisper.py 的导入路径

- config 和 utils 改为 common 模块导入

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 18: 更新 src/__init__.py

**Files:**
- Modify: `src/__init__.py`

- [ ] **Step 1: 读取当前内容**

```bash
cat src/__init__.py
```

- [ ] **Step 2: 更新 src/__init__.py**

将文件内容更新为新的导入路径，如果原文件为空或只是简单的导出，创建新的内容：

```python
"""wh_graphrag_re 核心模块"""

# 导入各子模块的公共接口
from .rag import (
    RAGRetriever,
    GraphRAGRetriever,
    UnifiedRAGManager,
    get_rag_instance,
    get_graph_rag_instance,
    get_unified_rag_manager,
    initialize_rag_system,
)
from .vlm import get_vlm_instance, VLM_NAME
from .asr import WhisperASR, get_asr_instance
from .parser import PortInstructionParser, parse_port_instruction
from .common import settings, get_device, get_reranker_instance

__all__ = [
    # RAG
    'RAGRetriever',
    'GraphRAGRetriever',
    'UnifiedRAGManager',
    'get_rag_instance',
    'get_graph_rag_instance',
    'get_unified_rag_manager',
    'initialize_rag_system',
    # VLM
    'get_vlm_instance',
    'VLM_NAME',
    # ASR
    'WhisperASR',
    'get_asr_instance',
    # Parser
    'PortInstructionParser',
    'parse_port_instruction',
    # Common
    'settings',
    'get_device',
    'get_reranker_instance',
]
```

- [ ] **Step 3: 验证 Python 语法正确**

```bash
python -m py_compile src/__init__.py
```

Expected: 无错误输出

- [ ] **Step 4: 提交**

```bash
git add src/__init__.py
git commit -m "refactor: 更新 src/__init__.py 导入路径

- 更新为新的子模块结构
- 提供统一的模块级导出

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 19: 更新 main_interaction.py 的导入

**Files:**
- Modify: `main_interaction.py`

- [ ] **Step 1: 查看当前导入**

```bash
grep -n "^from src\." main_interaction.py | head -20
```

- [ ] **Step 2: 更新导入语句**

根据需要将：
```python
from src.vlm import get_vlm_instance
from src.asr import get_asr_instance
from src.parser import parse_port_instruction
from src.rag_manager import get_unified_rag_manager
from src.config import settings
from src.utils import get_device
```

替换为（使用便捷导入）：
```python
from src.vlm import get_vlm_instance
from src.asr import get_asr_instance
from src.parser import parse_port_instruction
from src.rag import get_unified_rag_manager
from src.common import settings, get_device
```

- [ ] **Step 3: 验证 Python 语法正确**

```bash
python -m py_compile main_interaction.py
```

Expected: 无错误输出

- [ ] **Step 4: 提交**

```bash
git add main_interaction.py
git commit -m "refactor: 更新 main_interaction.py 的导入路径

- 适配新的 src/ 目录结构
- 使用子模块便捷导入

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 20: 更新 main_rag.py 的导入

**Files:**
- Modify: `main_rag.py`

- [ ] **Step 1: 查看当前导入**

```bash
grep -n "^from src\." main_rag.py | head -20
```

- [ ] **Step 2: 更新导入语句**

根据需要将：
```python
from src.rag import RAGRetriever
from src.graph_rag import GraphRAGRetriever
from src.rag_manager import initialize_rag_system, get_unified_rag_manager
from src.config import settings
```

替换为：
```python
from src.rag import RAGRetriever, GraphRAGRetriever
from src.rag import initialize_rag_system, get_unified_rag_manager
from src.common import settings
```

- [ ] **Step 3: 验证 Python 语法正确**

```bash
python -m py_compile main_rag.py
```

Expected: 无错误输出

- [ ] **Step 4: 提交**

```bash
git add main_rag.py
git commit -m "refactor: 更新 main_rag.py 的导入路径

- 适配新的 src/ 目录结构
- 使用 RAG 子模块便捷导入

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 21: 更新 VLM 服务器脚本的导入

**Files:**
- Modify: `start_vlm_server.py`
- Modify: `status_vlm_server.py`
- Modify: `stop_vlm_server.py`

- [ ] **Step 1: 更新 start_vlm_server.py 的导入**

将：
```python
from src.config import settings
from src.vlm_server import get_vlm_server_manager
```

替换为：
```python
from src.common.config import settings
from src.vlm.server import get_vlm_server_manager
```

- [ ] **Step 2: 更新 status_vlm_server.py 的导入**

将：
```python
from src.config import settings
from src.vlm_server import get_vlm_server_manager
```

替换为：
```python
from src.common.config import settings
from src.vlm.server import get_vlm_server_manager
```

- [ ] **Step 3: 更新 stop_vlm_server.py 的导入**

将：
```python
from src.config import settings
from src.vlm_server import get_vlm_server_manager
```

替换为：
```python
from src.common.config import settings
from src.vlm.server import get_vlm_server_manager
```

- [ ] **Step 4: 验证 Python 语法正确**

```bash
python -m py_compile start_vlm_server.py status_vlm_server.py stop_vlm_server.py
```

Expected: 无错误输出

- [ ] **Step 5: 提交**

```bash
git add start_vlm_server.py status_vlm_server.py stop_vlm_server.py
git commit -m "refactor: 更新 VLM 服务器脚本的导入路径

- 适配新的 src/ 目录结构

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 22: 更新测试文件的导入

**Files:**
- Modify: `tests/test_reranker.py`
- Modify: `tests/test_graph_rag_reranker.py`
- Modify: `test_rag_context.py`

- [ ] **Step 1: 更新 tests/test_reranker.py 的导入**

将：
```python
from src.reranker import get_reranker_instance
```

替换为：
```python
from src.common.reranker import get_reranker_instance
```

- [ ] **Step 2: 更新 tests/test_graph_rag_reranker.py 的导入**

将：
```python
from src.reranker import get_reranker_instance
from src.graph_rag import GraphRAGRetriever
from src.config import settings
```

替换为：
```python
from src.common.reranker import get_reranker_instance
from src.rag import GraphRAGRetriever
from src.common.config import settings
```

- [ ] **Step 3: 更新 test_rag_context.py 的导入**

将：
```python
from src.rag_manager import initialize_rag_system
```

替换为：
```python
from src.rag import initialize_rag_system
```

- [ ] **Step 4: 验证 Python 语法正确**

```bash
python -m py_compile tests/test_reranker.py tests/test_graph_rag_reranker.py test_rag_context.py
```

Expected: 无错误输出

- [ ] **Step 5: 提交**

```bash
git add tests/test_reranker.py tests/test_graph_rag_reranker.py test_rag_context.py
git commit -m "refactor(tests): 更新测试文件的导入路径

- 适配新的 src/ 目录结构

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 23: 验证所有模块导入

**Files:** None (verification task)

- [ ] **Step 1: 验证所有子模块可以正确导入**

```bash
python -c "from src.rag import *; from src.vlm import *; from src.asr import *; from src.parser import *; from src.common import *; print('✓ 所有子模块导入成功')"
```

Expected output: `✓ 所有子模块导入成功`

- [ ] **Step 2: 验证主入口文件可以正确导入**

```bash
python -c "import main_interaction; import main_rag; print('✓ 主入口文件导入成功')"
```

Expected output: `✓ 主入口文件导入成功`

- [ ] **Step 3: 验证测试文件可以正确导入**

```bash
python -m pytest tests/test_reranker.py tests/test_graph_rag_reranker.py --collect-only -q
```

Expected output: 显示收集到的测试数量，无错误

- [ ] **Step 4: 提交验证**

```bash
git log --oneline -5
```

Expected: 显示最近的提交记录

---

## Task 24: 运行完整测试套件

**Files:** None (testing task)

- [ ] **Step 1: 运行所有测试**

```bash
python -m pytest tests/ -v
```

Expected: 所有测试通过

- [ ] **Step 2: 如果测试失败，检查并修复**

如果失败：
```bash
# 查看详细错误
python -m pytest tests/ -v --tb=short

# 修复问题后重新运行
python -m pytest tests/ -v
```

- [ ] **Step 3: 提交测试结果（如果有修复）**

```bash
git add .
git commit -m "test: 确保所有测试通过

- 验证重构后的代码功能正常
- 所有测试用例通过

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 25: 更新 CLAUDE.md 文档

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 更新 CLAUDE.md 中的模块结构说明**

找到 "Module Structure" 或 "### Module Structure" 部分，更新为：

```markdown
**Core Processing** (`src/`):
- `src/config.py` → **`src/common/config.py`**: Pydantic Settings - All configuration from environment variables
- `src/vlm.py` → **`src/vlm/router.py`**: Unified VLM Entry - Dynamic model selection router
- `src/qwen2vlm.py` → **`src/vlm/qwen2.py`**: Qwen2VLM - vLLM client implementation
- `src/qwen35vlm.py` → **`src/vlm/qwen35.py`**: Qwen35VLM - vLLM client implementation
- `src/vlm_server.py` → **`src/vlm/server.py`**: VLLMServerManager - vLLM server lifecycle management
- `src/asr.py` → **`src/asr/whisper.py`**: WhisperASR - Audio transcription with LRU caching
- `src/parser.py` → **`src/parser/parser.py`**: PortInstructionParser - Schema definition + rule-based fallback
- `src/rag_manager.py` → **`src/rag/manager.py`**: UnifiedRAGManager - Single entry point for both RAG modes
- `src/rag.py` → **`src/rag/traditional.py`**: RAGRetriever - Traditional vector + BM25 retrieval
- `src/graph_rag.py` → **`src/rag/graph.py`**: GraphRAGRetriever - Knowledge graph retrieval
- `src/reranker.py` → **`src/common/reranker.py`**: RerankerManager - Unified BGE Reranker service
- `src/utils.py` → **`src/common/utils.py`**: Device selection and image conversion utilities
- `src/graph_extractors.py` → **`src/rag/graph_extractors.py`**: Knowledge graph extractors
```

- [ ] **Step 2: 更新导入示例**

找到文档中的导入示例，更新为新的路径，例如：

```python
# 旧示例
from src.rag import RAGRetriever
from src.vlm import get_vlm_instance

# 新示例（两种方式）
# 方式 1: 详细导入（推荐）
from src.rag.traditional import RAGRetriever
from src.vlm.router import get_vlm_instance

# 方式 2: 便捷导入（向后兼容）
from src.rag import RAGRetriever
from src.vlm import get_vlm_instance
```

- [ ] **Step 3: 提交文档更新**

```bash
git add CLAUDE.md
git commit -m "docs: 更新 CLAUDE.md 以反映新的目录结构

- 更新模块结构说明
- 更新导入示例代码
- 说明详细导入和便捷导入两种方式

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 26: 最终验证和推送

**Files:** None (final verification)

- [ ] **Step 1: 最终导入验证**

```bash
python -c "
from src.rag import RAGRetriever, GraphRAGRetriever, get_unified_rag_manager
from src.vlm import get_vlm_instance, VLM_NAME
from src.asr import get_asr_instance
from src.parser import parse_port_instruction
from src.common import settings, get_device
print('✓ 所有导入验证通过')
print(f'VLM_NAME: {VLM_NAME}')
"
```

Expected: 显示 VLM_NAME 且无错误

- [ ] **Step 2: 检查项目状态**

```bash
git status
```

Expected: working tree clean

- [ ] **Step 3: 推送所有提交到远程**

```bash
git push origin feature/warehouse-scheduling-mvp
```

Expected: 推送成功

- [ ] **Step 4: 创建总结性提交（如果需要）**

```bash
git commit --allow-empty -m "refactor: 完成 src/ 目录重组

- 按技术栈分组为 rag/, vlm/, asr/, parser/, common/
- 提供便捷导入支持向后兼容
- 更新所有相关文件的导入路径
- 所有测试通过

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push
```

---

## 回滚计划

如果在任何步骤中遇到无法解决的问题，执行回滚：

```bash
# 回滚所有 src/ 目录的更改
git checkout HEAD -- src/

# 回滚主程序的更改
git checkout HEAD -- main_interaction.py main_rag.py start_vlm_server.py status_vlm_server.py stop_vlm_server.py

# 回滚测试文件的更改
git checkout HEAD -- tests/ test_rag_context.py

# 回滚文档更改
git checkout HEAD -- CLAUDE.md
```

---

## 完成标准

- [ ] 所有文件已移动到新位置
- [ ] 所有 `__init__.py` 文件已创建
- [ ] 所有导入语句已更新
- [ ] 所有测试通过
- [ ] 文档已更新
- [ ] 代码已推送到远程仓库

---

## 预计时间

- 文件移动和目录创建: 10 分钟
- 创建 __init__.py 文件: 10 分钟
- 更新内部导入: 20 分钟
- 更新外部导入: 15 分钟
- 测试验证: 15 分钟
- 文档更新: 10 分钟

**总计**: 约 1.5 小时
