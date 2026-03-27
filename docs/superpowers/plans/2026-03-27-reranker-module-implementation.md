# GraphRAG Reranker 独立模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建独立的 Reranker 模块，在 GraphRAG 中集成重排序功能，提升检索准确性

**Architecture:**
1. 提取公共 Reranker 逻辑到独立模块 `src/reranker.py`，使用单例模式全局共享实例
2. 修改 `src/rag.py` 和 `src/graph_rag.py`，统一使用新模块（去除重复代码）
3. 配置化控制 Reranker 启用/禁用，支持运行时切换

**Tech Stack:** Python 3.10+, FlagEmbedding (BGE-reranker-v2-m3), Pydantic Settings, pytest

---

## 文件结构概览

```
src/
├── reranker.py          # ✅ 新建：独立的 Reranker 模块
│   └── 职责：封装 BGE Reranker，提供统一的重排序 API
│
├── rag.py               # 🔧 修改：使用新模块，删除重复代码
│   └── 变更：
│       - 删除 _initialize_reranker() 方法
│       - 删除 _rerank_results() 方法
│       - 修改 __init__() 使用 get_reranker_instance()
│       - 修改 retrieve() 调用新 API
│
├── graph_rag.py         # 🔧 修改：集成 Reranker
│   └── 变更：
│       - 新增导入 get_reranker_instance
│       - 修改 __init__() 初始化 reranker
│       - 修改 retrieve() 添加 reranker 精排步骤
│
└── config.py            # 🔧 修改：新增 GraphRAG Reranker 配置
    └── 变更：
        - 新增 GraphRerankConfig 类
        - 在 Config 类中添加 graph_rerank 字段

tests/
├── __init__.py                   # ✅ 新建：测试包初始化
├── test_reranker.py              # ✅ 新建：Reranker 模块单元测试
│   └── 职责：测试 RerankerManager 的初始化、重排序、单例模式
│
└── test_graph_rag_reranker.py    # ✅ 新建：GraphRAG 集成测试
    └── 职责：测试 GraphRAG + Reranker 的端到端功能

.env.example                     # 🔧 修改：新增配置项
```

---

## Task 0: 验证前置条件

**Files:**
- Create: `tests/__init__.py`

- [ ] **Step 1: 创建 tests 目录结构**

```bash
# 创建 tests 目录
mkdir -p tests

# 创建 __init__.py 使其成为 Python 包
touch tests/__init__.py
```

- [ ] **Step 2: 验证 pytest 是否已安装**

```bash
# 检查 pytest 是否已安装
pip list | grep pytest

# 如果未安装，安装 pytest
pip install pytest pytest-cov
```

预期: pytest 已安装或成功安装

- [ ] **Step 3: 验证 FlagEmbedding 是否已安装**

```bash
# 检查 FlagEmbedding 是否已安装
pip list | grep FlagEmbedding

# 如果未安装，安装 FlagEmbedding
pip install -U FlagEmbedding
```

预期: FlagEmbedding 已安装或成功安装

- [ ] **Step 4: 提交前置条件**

```bash
git add tests/__init__.py
git commit -m "test: 创建 tests 目录结构

- 创建 tests 目录
- 添加 __init__.py 使其成为 Python 包
- 验证 pytest 和 FlagEmbedding 依赖

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 1: 创建独立的 Reranker 模块

**Files:**
- Create: `src/reranker.py`

**目标：** 封装 BGE Reranker 初始化和使用逻辑，提供单例模式的全局访问点

- [ ] **Step 1: 创建 `src/reranker.py` 文件并编写基础结构**

```python
"""
Reranker 模块：统一的文档重排序服务

功能：
- 封装 BGE Reranker 初始化
- 提供单例模式，全局共享模型
- 统一的重排序接口
- 错误处理和降级策略
"""
import logging
from functools import lru_cache
from typing import Dict, List, Optional

from src.config import config
from src.utils import get_device

logger = logging.getLogger(__name__)


class RerankerManager:
    """Reranker 管理器（单例模式）"""

    def __init__(self):
        self._reranker = None
        self._model_name = None
        self._device = None
        self._initialized = False

        # 延迟初始化，按需加载
        if config.rerank.enabled:
            self._initialize()

    def _initialize(self) -> bool:
        """初始化 Reranker 模型"""
        if self._initialized:
            return True

        try:
            from FlagEmbedding import FlagReranker

            self._model_name = config.rerank.model
            self._device = get_device(config.rerank.device)

            logger.info(f"正在加载 Reranker 模型: {self._model_name} 在 {self._device} 上...")
            self._reranker = FlagReranker(
                self._model_name,
                device=self._device
            )
            self._initialized = True
            logger.info(f"✅ Reranker 模型加载完成: {self._model_name}")
            return True

        except ImportError as e:
            logger.warning(f"FlagEmbedding 库未安装: {e}")
            logger.warning("安装方法: pip install -U FlagEmbedding")
            return False
        except Exception as e:
            logger.error(f"Reranker 初始化失败: {e}")
            return False

    def rerank(
        self,
        query: str,
        results: List[Dict],
        top_k: Optional[int] = None
    ) -> List[Dict]:
        """
        对检索结果进行重排序

        Args:
            query: 查询文本
            results: 检索结果列表，每个元素包含 'text' 字段
            top_k: 返回前 K 个结果，None 表示返回全部

        Returns:
            重排序后的结果列表，每个元素增加 'rerank_score' 字段
        """
        # 延迟初始化
        if not self._initialized and not self._initialize():
            logger.warning("Reranker 未初始化，返回原始结果")
            return results

        if not results:
            return results

        try:
            # 提取文本
            texts = [r.get('text', '') for r in results]

            # 构建 query-document 对
            pairs = [[query, text] for text in texts]

            # 计算相关性分数
            scores = self._reranker.compute_score(pairs)

            # 添加分数到结果
            for i, result in enumerate(results):
                result['rerank_score'] = float(scores[i])

            # 按分数排序
            results.sort(key=lambda x: x['rerank_score'], reverse=True)

            # 记录日志
            max_score = max(r['rerank_score'] for r in results)
            avg_score = sum(r['rerank_score'] for r in results) / len(results)
            logger.info(
                f"Reranking 完成: {len(results)} 个结果, "
                f"最高分={max_score:.3f}, 平均分={avg_score:.3f}"
            )

            # 返回 Top-K
            if top_k is not None:
                return results[:top_k]
            return results

        except Exception as e:
            logger.error(f"Reranking 失败: {e}，返回原始结果")
            return results

    def is_enabled(self) -> bool:
        """检查 Reranker 是否可用"""
        return config.rerank.enabled and self._initialized

    def get_model_info(self) -> Dict[str, any]:
        """获取模型信息"""
        return {
            'enabled': config.rerank.enabled,
            'initialized': self._initialized,
            'model': self._model_name,
            'device': str(self._device) if self._device else None
        }


# 全局单例
@lru_cache(maxsize=1)
def get_reranker_instance() -> RerankerManager:
    """
    获取 Reranker 单例实例

    Returns:
        RerankerManager: 全局唯一的 Reranker 实例
    """
    return RerankerManager()


# 便捷函数
def rerank_results(
    query: str,
    results: List[Dict],
    top_k: Optional[int] = None
) -> List[Dict]:
    """
    便捷函数：对检索结果进行重排序

    Args:
        query: 查询文本
        results: 检索结果列表
        top_k: 返回前 K 个结果

    Returns:
        重排序后的结果列表
    """
    reranker = get_reranker_instance()
    return reranker.rerank(query, results, top_k=top_k)
```

- [ ] **Step 2: 验证文件语法**

运行: `python -m py_compile src/reranker.py`
预期: 无语法错误

- [ ] **Step 3: 提交初始代码**

```bash
git add src/reranker.py
git commit -m "feat: 创建独立的 Reranker 模块

- 封装 BGE Reranker 初始化逻辑
- 提供单例模式，全局共享模型实例
- 实现统一的重排序接口
- 支持错误处理和降级策略

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 为 Reranker 模块编写单元测试

**Files:**
- Create: `tests/test_reranker.py`

- [ ] **Step 1: 创建测试文件**

```python
"""
Reranker 模块单元测试
"""
import pytest
from src.reranker import get_reranker_instance, RerankerManager, rerank_results


def test_reranker_singleton():
    """测试单例模式"""
    reranker1 = get_reranker_instance()
    reranker2 = get_reranker_instance()
    assert reranker1 is reranker2


def test_reranker_initialization():
    """测试初始化"""
    reranker = get_reranker_instance()
    info = reranker.get_model_info()

    # 验证初始化状态
    assert 'enabled' in info
    assert 'initialized' in info
    assert 'model' in info
    assert 'device' in info


def test_rerank_results():
    """测试重排序功能"""
    reranker = get_reranker_instance()
    if not reranker.is_enabled():
        pytest.skip("Reranker 未启用")

    query = "bwpg"
    results = [
        {'text': '堆取料机斗轮总成 (BWA)'},
        {'text': '斗轮驱动行星减速机 (BW-PG)'},
        {'text': '传送带驱动滚筒 (BCDP)'},
    ]

    reranked = reranker.rerank(query, results)

    # 验证结果包含 rerank_score
    assert all('rerank_score' in r for r in reranked)

    # 验证结果已排序（降序）
    scores = [r['rerank_score'] for r in reranked]
    assert scores == sorted(scores, reverse=True)


def test_rerank_top_k():
    """测试 Top-K 截断"""
    reranker = get_reranker_instance()
    if not reranker.is_enabled():
        pytest.skip("Reranker 未启用")

    results = [
        {'text': f'结果 {i}'}
        for i in range(10)
    ]

    top_3 = reranker.rerank("test", results, top_k=3)
    assert len(top_3) == 3


def test_empty_results():
    """测试空结果"""
    reranker = get_reranker_instance()
    empty = reranker.rerank("test", [])
    assert empty == []


def test_model_info():
    """测试模型信息"""
    reranker = get_reranker_instance()
    info = reranker.get_model_info()

    assert info['enabled'] in [True, False]
    assert info['initialized'] in [True, False]
    assert isinstance(info['model'], (str, type(None)))
    assert isinstance(info['device'], (str, type(None)))


def test_convenience_function():
    """测试便捷函数"""
    if not get_reranker_instance().is_enabled():
        pytest.skip("Reranker 未启用")

    results = [
        {'text': '测试结果 1'},
        {'text': '测试结果 2'},
    ]

    reranked = rerank_results("test", results)
    assert len(reranked) == len(results)
    assert all('rerank_score' in r for r in reranked)
```

- [ ] **Step 2: 运行测试**

```bash
# 确保安装 pytest
pip install pytest pytest-cov

# 运行测试
pytest tests/test_reranker.py -v
```

预期: 部分测试通过（如果 Reranker 未启用，会跳过某些测试）

- [ ] **Step 3: 提交测试文件**

```bash
git add tests/test_reranker.py
git commit -m "test: 添加 Reranker 模块单元测试

- 测试单例模式
- 测试初始化功能
- 测试重排序功能
- 测试 Top-K 截断
- 测试空结果处理
- 测试便捷函数

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 修改 config.py 新增 GraphRAG Reranker 配置

**Files:**
- Modify: `src/config.py:124-126` (在 ChunkingConfig 类之后，GraphRAGConfig 类之前)

- [ ] **Step 1: 添加 GraphRerankConfig 配置类**

在 `src/config.py` 文件中，在 `RerankConfig` 类定义之后（约第 140 行），添加：

```python
class GraphRerankConfig(BaseAppConfig):
    """GraphRAG Reranker 配置"""
    enabled: bool = Field(default=False, alias="GRAPH_RERANK_ENABLED")
    top_k: int = Field(default=10, alias="GRAPH_RERANK_TOP_K")
    final_top_k: int = Field(default=3, alias="GRAPH_RERANK_FINAL_TOP_K")
```

- [ ] **Step 2: 在 Config 类中添加 graph_rerank 字段**

找到 `class Config(BaseSettings):` 定义，在现有的配置字段定义区域（约第 199-214 行），在 `graph_performance: GraphPerformanceConfig = GraphPerformanceConfig()` 之后添加：

```python
    # GraphRAG Reranker 配置
    graph_rerank: GraphRerankConfig = GraphRerankConfig()
```

注意：确保添加在 `model_config = SettingsConfigDict(...)` 之前（约第 216 行）

- [ ] **Step 3: 验证配置语法**

```bash
python -c "from src.config import config; print('GraphRerank enabled:', config.graph_rerank.enabled)"
```

预期: 无错误，输出 `GraphRerank enabled: False`

- [ ] **Step 4: 提交配置修改**

```bash
git add src/config.py
git commit -m "feat(config): 新增 GraphRAG Reranker 配置

- 添加 GraphRerankConfig 配置类
- 支持 enabled, top_k, final_top_k 参数
- 集成到全局 Config 类

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 修改传统 RAG (src/rag.py) 使用新模块

**Files:**
- Modify: `src/rag.py:105-114` (删除 _initialize_reranker)
- Modify: `src/rag.py:453-472` (删除 _rerank_results)
- Modify: `src/rag.py:1-10` (新增导入)
- Modify: `src/rag.py:37-53` (修改初始化)
- Modify: `src/rag.py:259-284` (修改检索方法)

- [ ] **Step 1: 新增导入语句**

在文件顶部的导入区域（约第 1-10 行），添加：

```python
from src.reranker import get_reranker_instance
```

- [ ] **Step 2: 删除 _initialize_reranker 方法**

找到并删除以下代码块（约第 105-114 行）：

```python
# ❌ 删除这段代码
def _initialize_reranker(self):
    """初始化BGE重排序器"""
    try:
        from FlagEmbedding import FlagReranker
        device = get_device(config.rerank.device)
        self.reranker = FlagReranker(config.rerank.model, device=device)
        logger.info(f"Reranker已加载: {config.rerank.model}")
    except Exception as e:
        logger.warning(f"Reranker初始化失败: {e}，reranking功能将禁用")
        self.reranker = None
```

- [ ] **Step 3: 修改 __init__ 方法**

找到 `def __init__(self):` 方法（约第 40 行），在 `_initialize_splitter()` 调用之后（约第 76 行），替换原来的 reranker 初始化代码：

**原代码**（删除）：
```python
        # 3. 初始化reranker
        if config.rerank.enabled:
            self._initialize_reranker()
```

**新代码**（添加）：
```python
        # 3. 获取 Reranker 实例（全局单例）
        self.reranker = get_reranker_instance()
```

- [ ] **Step 4: 修改 retrieve 方法使用新 API**

找到 `def retrieve(self, query: str) -> List[Dict[str, Any]]:` 方法（约第 259 行），找到 reranker 调用部分（约第 280-282 行）：

**原代码**：
```python
        # Reranking
        if self.reranker and results and config.rerank.enabled:
            results = self._rerank_results(query, results)
```

**新代码**：
```python
        # Reranking
        if config.rerank.enabled and self.reranker.is_enabled():
            results = self.reranker.rerank(
                query,
                results,
                top_k=config.rerank.final_top_k
            )
```

- [ ] **Step 5: 删除 _rerank_results 方法**

找到并删除以下整个方法（约第 453-472 行）：

```python
# ❌ 删除这段代码
def _rerank_results(self, query: str, results: List[Dict]) -> List[Dict]:
    """使用reranker重新排序"""
    if not results:
        return results

    try:
        texts = [r['text'] for r in results]
        pairs = [[query, text] for text in texts]
        scores = self.reranker.compute_score(pairs)

        for i, result in enumerate(results):
            result['rerank_score'] = float(scores[i])

        results.sort(key=lambda x: x['rerank_score'], reverse=True)
        logger.info(f"Reranking完成，最高分: {max(r['rerank_score'] for r in results):.3f}")
        return results

    except Exception as e:
        logger.warning(f"Reranking失败: {e}")
        return results
```

- [ ] **Step 6: 验证修改**

```bash
# 检查语法
python -m py_compile src/rag.py

# 测试导入
python -c "from src.rag import RAGRetriever; print('Import OK')"
```

预期: 无错误

- [ ] **Step 7: 提交修改**

```bash
git add src/rag.py
git commit -m "refactor(rag): 使用独立 Reranker 模块

- 删除重复的 _initialize_reranker() 方法
- 删除重复的 _rerank_results() 方法
- 使用 get_reranker_instance() 获取全局单例
- 调用统一的重排序 API

代码减少约 70 行

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: 修改 GraphRAG (src/graph_rag.py) 集成 Reranker

**Files:**
- Modify: `src/graph_rag.py:1-20` (新增导入)
- Modify: `src/graph_rag.py:72-83` (修改初始化)
- Modify: `src/graph_rag.py:213-243` (修改检索方法)

- [ ] **Step 1: 新增导入语句**

在文件顶部的导入区域（约第 1-20 行），添加：

```python
from src.reranker import get_reranker_instance
```

- [ ] **Step 2: 修改 __init__ 方法初始化 reranker**

找到 `GraphRAGRetriever` 类的 `def __init__(self):` 方法（约第 72 行），在 `self._initialize_graph_retriever()` 之后（约第 109 行）添加：

```python
        # 初始化 Reranker
        self.reranker = get_reranker_instance()
        if self.reranker.is_enabled():
            logger.info("Reranker 已集成到 GraphRAG")
```

- [ ] **Step 3: 修改 retrieve 方法集成 reranker**

找到 `def retrieve(self, query: str) -> List[Dict[str, Any]]:` 方法（约第 213 行），在缓存更新之前添加 reranker 精排逻辑。

**原代码**（约第 233-243 行）：
```python
        # 图检索
        graph_results = self._retrieve_graph(query) if self.graph_retriever else []

        # 更新缓存
        if config.graph_performance.query_cache_ttl > 0:
            self._update_cache(query, graph_results)
```

**新代码**：
```python
        # 图检索
        graph_results = self._retrieve_graph(query) if self.graph_retriever else []

        # Reranker 精排
        if config.graph_rerank.enabled and self.reranker.is_enabled():
            logger.info(f"Reranker 精排前: {len(graph_results)} 个候选")
            graph_results = self.reranker.rerank(
                query,
                graph_results,
                top_k=config.graph_rerank.final_top_k
            )

        # 更新缓存（缓存 reranker 后的结果）
        if config.graph_performance.query_cache_ttl > 0:
            self._update_cache(query, graph_results)
```

- [ ] **Step 4: 验证修改**

```bash
# 检查语法
python -m py_compile src/graph_rag.py

# 测试导入
python -c "from src.graph_rag import GraphRAGRetriever; print('Import OK')"
```

预期: 无错误

- [ ] **Step 5: 提交修改**

```bash
git add src/graph_rag.py
git commit -m "feat(graph_rag): 集成 Reranker 精排功能

- 新增 reranker 实例初始化
- 在 retrieve() 方法中添加 reranker 精排步骤
- 支持通过配置启用/禁用
- 缓存 reranker 后的结果

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 更新 .env.example 配置文件

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: 新增 GraphRAG Reranker 配置项**

在 `.env.example` 文件中找到 Reranker 配置部分，添加：

```bash
# GraphRAG Reranker 配置
GRAPH_RERANK_ENABLED=true                    # 启用 GraphRAG Reranker
GRAPH_RERANK_TOP_K=10                        # 精排前保留的候选数
GRAPH_RERANK_FINAL_TOP_K=3                   # 最终返回给 VLM 的结果数
```

如果已有 RAG_RERANK_* 配置，确保它们在前面：
```bash
# Reranker 全局配置（传统 RAG 和 GraphRAG 共享）
RAG_RERANK_ENABLED=true
RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3
RAG_RERANK_DEVICE=auto
RAG_RERANK_TOP_K=10
RAG_RERANK_FINAL_TOP_K=3
```

- [ ] **Step 2: 提交配置文件**

```bash
git add .env.example
git commit -m "docs(config): 新增 GraphRAG Reranker 配置示例

- 添加 GRAPH_RERANK_ENABLED 开关
- 添加 GRAPH_RERANK_TOP_K 候选数量配置
- 添加 GRAPH_RERANK_FINAL_TOP_K 返回数量配置

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: 编写 GraphRAG 集成测试

**Files:**
- Create: `tests/test_graph_rag_reranker.py`

- [ ] **Step 1: 创建集成测试文件**

```python
"""
GraphRAG + Reranker 集成测试
"""
import pytest
from src.graph_rag import GraphRAGRetriever
from src.config import config


def test_graph_rag_with_reranker_enabled():
    """测试启用 Reranker 的 GraphRAG 检索"""
    # 确保启用
    original_enabled = config.graph_rerank.enabled
    config.graph_rerank.enabled = True

    try:
        retriever = GraphRAGRetriever()

        if not retriever.is_enabled():
            pytest.skip("GraphRAG 未启用")

        # 测试检索
        results = retriever.retrieve("bwpg")

        # 验证返回结果
        assert isinstance(results, list)

        # 验证包含 rerank_score
        if config.graph_rerank.enabled and retriever.reranker.is_enabled():
            for result in results:
                assert 'rerank_score' in result
                assert isinstance(result['rerank_score'], float)

    finally:
        # 恢复原始配置
        config.graph_rerank.enabled = original_enabled


def test_graph_rag_with_reranker_disabled():
    """测试禁用 Reranker 的 GraphRAG 检索"""
    original_enabled = config.graph_rerank.enabled
    config.graph_rerank.enabled = False

    try:
        retriever = GraphRAGRetriever()

        if not retriever.is_enabled():
            pytest.skip("GraphRAG 未启用")

        results = retriever.retrieve("bwpg")

        # 验证不包含 rerank_score
        for result in results:
            assert 'rerank_score' not in result

    finally:
        config.graph_rerank.enabled = original_enabled


def test_reranker_abbreviation_accuracy():
    """测试缩写识别准确率"""
    original_enabled = config.graph_rerank.enabled
    config.graph_rerank.enabled = True

    try:
        retriever = GraphRAGRetriever()

        if not retriever.is_enabled():
            pytest.skip("GraphRAG 未启用")

        test_cases = [
            ("bwpg", "斗轮驱动行星减速机"),  # 应该匹配到 BW-PG
            ("bcdp", "皮带机驱动滚筒"),       # 应该匹配到 BCDP
            ("bcbp", "皮带机改向滚筒"),       # 应该匹配到 BP-800×1800
        ]

        for query, expected_keyword in test_cases:
            results = retriever.retrieve(query)

            if results:
                # 验证第一个结果包含期望的关键词
                first_result_text = results[0]['text']
                assert expected_keyword in first_result_text, \
                    f"查询 '{query}' 的第一个结果应包含 '{expected_keyword}'，实际为: {first_result_text}"

    finally:
        config.graph_rerank.enabled = original_enabled


@pytest.mark.performance
def test_reranker_performance_latency():
    """测试 Reranker 性能延迟"""
    import time

    original_enabled = config.graph_rerank.enabled
    config.graph_rerank.enabled = True

    try:
        retriever = GraphRAGRetriever()

        if not retriever.is_enabled() or not retriever.reranker.is_enabled():
            pytest.skip("GraphRAG 或 Reranker 未启用")

        # 预热
        retriever.retrieve("bwpg")

        # 正式测试
        start = time.time()
        results = retriever.retrieve("bwpg")
        elapsed = time.time() - start

        # 验证延迟在可接受范围内（< 500ms）
        assert elapsed < 0.5, f"检索延迟 {elapsed:.3f}s 超过 500ms 限制"

        print(f"  → 检索延迟: {elapsed*1000:.2f}ms")

    finally:
        config.graph_rerank.enabled = original_enabled


def test_reranker_cache_integration():
    """测试 Reranker 与缓存的集成"""
    import time

    original_enabled = config.graph_rerank.enabled
    config.graph_rerank.enabled = True

    try:
        retriever = GraphRAGRetriever()

        if not retriever.is_enabled():
            pytest.skip("GraphRAG 未启用")

        query = "bwpg"

        # 第一次检索（应该触发 reranker）
        start1 = time.time()
        results1 = retriever.retrieve(query)
        time1 = time.time() - start1

        # 第二次检索（应该命中缓存）
        start2 = time.time()
        results2 = retriever.retrieve(query)
        time2 = time.time() - start2

        # 缓存应该更快
        assert time2 < time1, "缓存命中应该比首次检索快"

        # 结果应该一致
        assert len(results1) == len(results2)

        print(f"  → 首次检索: {time1*1000:.2f}ms, 缓存命中: {time2*1000:.2f}ms")

    finally:
        config.graph_rerank.enabled = original_enabled
```

- [ ] **Step 2: 运行集成测试**

```bash
# 运行集成测试
pytest tests/test_graph_rag_reranker.py -v

# 运行性能测试
pytest tests/test_graph_rag_reranker.py::test_reranker_performance_latency -v -s
```

预期: 所有测试通过（部分测试可能需要 GraphRAG 启用）

- [ ] **Step 3: 提交测试文件**

```bash
git add tests/test_graph_rag_reranker.py
git commit -m "test: 添加 GraphRAG Reranker 集成测试

- 测试启用/禁用 Reranker 的场景
- 测试缩写识别准确率
- 测试性能延迟（< 500ms）
- 测试与缓存系统的集成

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: 性能基准记录（实施前）

**Files:**
- Modify: 无

- [ ] **Step 1: 记录当前性能基线**

在实施修改之前，先记录当前系统的性能作为对比基准：

```bash
# 创建性能基准脚本
cat > /tmp/benchmark_baseline.py << 'EOF'
import time
from src.graph_rag import GraphRAGRetriever

retriever = GraphRAGRetriever()

if not retriever.is_enabled():
    print("GraphRAG 未启用，无法记录基准")
    exit(1)

queries = ["bwpg", "bcdp", "sdpg", "bcbp", "srsb"]

print("=== 性能基准（无 Reranker）===")
for query in queries:
    start = time.time()
    results = retriever.retrieve(query)
    elapsed = time.time() - start
    print(f"{query}: {elapsed*1000:.2f}ms, 结果数: {len(results)}")
EOF

# 运行基准测试
python /tmp/benchmark_baseline.py
```

预期: 记录所有查询的延迟时间，保存输出用于后续对比

---

## Task 9: 回归测试与验证

- [ ] **Step 2: 手动功能测试**

```bash
# 启用 GraphRAG Reranker
export GRAPH_RERANK_ENABLED=true

# 运行主程序
python main_interaction.py
```

**测试用例**：
```
[输入] > 需要5个bwpg
[输入] > 需要五个bcdp
[输入] > 需要五个sdpg
[输入] > 溜槽耐磨板需要维修
```

**验证点**：
- ✅ 检索成功，无错误
- ✅ 结果包含 `rerank_score` 字段
- ✅ 缩写识别准确率提升
- ✅ 字段完整性改善

- [ ] **Step 3: 性能基准测试**

```python
# 创建性能测试脚本
import time
from src.graph_rag import GraphRAGRetriever

retriever = GraphRAGRetriever()

queries = ["bwpg", "bcdp", "sdpg", "bcbp", "srsb"]

for query in queries:
    start = time.time()
    results = retriever.retrieve(query)
    elapsed = time.time() - start

    print(f"{query}: {elapsed*1000:.2f}ms, 结果数: {len(results)}")
```

预期: 所有查询延迟 < 500ms

- [ ] **Step 4: 提交最终验证**

```bash
# 如果所有测试通过，创建总结性提交
git commit --allow-empty -m "test: GraphRAG Reranker 模块验证通过

- 单元测试通过
- 集成测试通过
- 回归测试通过
- 手动功能测试通过
- 性能测试通过（< 500ms）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 10: 烟雾测试（Smoke Test）

**Files:**
- Modify: 无

- [ ] **Step 1: 运行烟雾测试**

```bash
# 综合烟雾测试
python -c "
import time
from src.reranker import get_reranker_instance
from src.config import config

# 测试 1: Reranker 模块导入
reranker = get_reranker_instance()
print('✅ Reranker 模块导入成功')

# 测试 2: 配置可用
print(f'✅ GraphRAG Reranker enabled: {config.graph_rerank.enabled}')
print(f'✅ GraphRAG Reranker top_k: {config.graph_rerank.top_k}')

# 测试 3: Reranker 初始化
if reranker.is_enabled():
    print(f'✅ Reranker 模型: {reranker.get_model_info()[\"model\"]}')
else:
    print('⚠️  Reranker 未启用（正常，如果配置禁用）')

print('\\n=== 所有烟雾测试通过 ===')
"
```

预期: 所有测试通过，无错误

- [ ] **Step 2: 提交烟雾测试**

```bash
git add -A
git commit -m "test: 烟雾测试通过 - 所有模块正常工作

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 11: 文档更新

**Files:**
- Modify: `CLAUDE.md` (可选，如果需要更新架构说明)

- [ ] **Step 1: 更新 CLAUDE.md（如有必要）**

在 `CLAUDE.md` 的 **核心处理** 部分的 RAG 章节，添加：

```markdown
### Reranker 模块

**独立模块** (`src/reranker.py`):
- 封装 BGE Reranker 初始化和使用
- 单例模式，全局共享模型实例
- 统一的重排序接口
- 传统 RAG 和 GraphRAG 都使用此模块

**配置**:
```bash
# 全局配置（传统 RAG 和 GraphRAG 共享）
RAG_RERANK_ENABLED=true
RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3

# GraphRAG 专用配置
GRAPH_RERANK_ENABLED=true
GRAPH_RERANK_TOP_K=10
GRAPH_RERANK_FINAL_TOP_K=3
```
```

- [ ] **Step 2: 提交文档更新**

```bash
git add CLAUDE.md
git commit -m "docs: 更新架构说明 - Reranker 独立模块

- 添加 Reranker 模块说明
- 更新配置示例
- 说明使用场景

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 总结与验证清单

完成所有任务后，请验证：

- [ ] **代码质量**
  - [ ] `src/reranker.py` 创建完成
  - [ ] `src/rag.py` 删除重复代码
  - [ ] `src/graph_rag.py` 集成 reranker
  - [ ] `src/config.py` 新增配置类
  - [ ] 代码无语法错误
  - [ ] 代码遵循项目风格

- [ ] **测试覆盖**
  - [ ] 单元测试 (`tests/test_reranker.py`) 通过
  - [ ] 集成测试 (`tests/test_graph_rag_reranker.py`) 通过
  - [ ] 回归测试通过
  - [ ] 手动功能测试通过

- [ ] **性能指标**
  - [ ] Reranker 延迟 < 200ms
  - [ ] 端到端延迟 < 500ms
  - [ ] 内存占用合理（共享单例）

- [ ] **功能验证**
  - [ ] 缩写识别率提升（bwpg, bcdp, sdpg）
  - [ ] 中文自然语言处理改善
  - [ ] 检索一致性提升
  - [ ] 配置启用/禁用正常工作

- [ ] **文档完整**
  - [ ] `.env.example` 更新
  - [ ] 代码注释清晰
  - [ ] CLAUDE.md 更新（可选）

---

## 预期成果

完成本计划后，系统将具备：

1. **独立的 Reranker 模块**：统一的接口，无代码重复
2. **GraphRAG 精排能力**：提升检索准确性和一致性
3. **配置化控制**：灵活启用/禁用 Reranker
4. **完整的测试覆盖**：单元测试 + 集成测试 + 性能测试
5. **代码质量提升**：减少约 70 行重复代码

---

**下一步**：审查此计划，确认无误后开始实施。
