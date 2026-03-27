# GraphRAG Reranker 独立模块设计文档

**文档日期**: 2026-03-27
**作者**: Claude Code
**状态**: 待审核

---

## 📋 目录

1. [问题背景](#问题背景)
2. [当前状态分析](#当前状态分析)
3. [需求分析](#需求分析)
4. [设计方案](#设计方案)
5. [架构设计](#架构设计)
6. [实现细节](#实现细节)
7. [测试策略](#测试策略)
8. [风险评估](#风险评估)
9. [实施计划](#实施计划)

---

## 问题背景

### 初始问题

用户测试发现 GraphRAG 在准确性方面存在问题：

1. **缩写识别率不稳定**：
   - `"bwpg"` → 部分字段缺失（installation_equipment, location, action_required）
   - `"bcdp"` → 几乎所有扩展字段都是 null
   - `"sdpg"` → part_name 只返回 "SDPG"，不是完整中文名称

2. **中文自然语言处理弱**：
   - `"溜槽耐磨板"` → 只有 action_required，其他字段都是 null

3. **检索一致性差**：
   - 相同类型的查询（如都是缩写）有时效果好有时效果差
   - VLM 推理时间波动大（0.56s - 12.06s）

### 根因分析

1. **缩写格式不匹配**：知识库使用 "BW-PG" 格式，用户输入 "bwpg" 格式
2. **GraphRAG 检索配置不足**：
   - `vector_top_k=5` 和 `synonym_max_keywords=8` 偏低
   - `path_depth=1` 限制了多跳推理
3. **GraphRAG 没有 Reranker**：
   - 传统 RAG 有 BGE-reranker 精排
   - GraphRAG 直接按原始分数返回，导致排序不够精准
4. **代码重复**：
   - `src/rag.py` 和 `src/graph_rag.py` 都有独立的 reranker 初始化代码
   - 每个模块独立加载模型，浪费资源

---

## 当前状态分析

### 系统架构

```
用户输入 (音频/文本/图片)
    ↓
main_interaction.py
    ├─ ASR 语音识别 (可选)
    ├─ VLM 推理
    │   ├─ RAG 检索 (自动触发)
    │   └─ 生成结构化 JSON
    └─ Parser 校验
    ↓
返回 PortInstruction
```

### Reranker 使用现状

| 模块 | Reranker | 代码位置 | 问题 |
|------|----------|---------|------|
| **传统 RAG** (`src/rag.py`) | ✅ 有 | 第 105-114 行, 453-472 行 | 代码重复 |
| **GraphRAG** (`src/graph_rag.py`) | ❌ 无 | - | 缺失精排 |

### 传统 RAG 的 Reranker 流程

```python
# src/rag.py
def retrieve(self, query: str):
    # 1. 检索
    results = self._retrieve_hybrid(query)  # 向量 + BM25 → 15 个

    # 2. Reranker 精排
    if self.reranker and results and config.rerank.enabled:
        results = self._rerank_results(query, results)

    # 3. 返回 Top-3
    return results[:config.rag.top_k]

def _rerank_results(self, query: str, results: List[Dict]):
    texts = [r['text'] for r in results]
    pairs = [[query, text] for text in texts]
    scores = self.reranker.compute_score(pairs)

    for i, result in enumerate(results):
        result['rerank_score'] = float(scores[i])

    results.sort(key=lambda x: x['rerank_score'], reverse=True)
    return results
```

### GraphRAG 当前的检索流程

```python
# src/graph_rag.py
def retrieve(self, query: str):
    # 1. 检查缓存
    if cache_key in self.query_cache:
        return cached['results']

    # 2. 图检索
    graph_results = self._retrieve_graph(query)  # 15 个候选

    # 3. ❌ 直接返回，没有 Reranker
    return graph_results[:config.rag.top_k]
```

---

## 需求分析

### 核心需求

1. **创建独立的 Reranker 模块**
   - 提取公共逻辑，避免代码重复
   - 使用单例模式，全局共享模型实例
   - 提供简洁的 API 接口

2. **在 GraphRAG 中集成 Reranker**
   - 在图检索后、返回前进行精排
   - 支持配置化启用/禁用
   - 保持与传统 RAG 的一致性

3. **性能要求**
   - 延迟增加 < 500ms
   - 不增加模型加载时间（复用现有模型）

### 非需求

- ❌ Reranker 不需要服务化部署（推理快，无并发需求）
- ❌ 不需要实现缓存（后续根据性能测试评估）
- ❌ 不需要更换 Reranker 模型（复用 BGE-reranker-v2-m3）

---

## 设计方案

### 方案概述

**方案名称**: GraphRAG Reranker 独立模块与集成

**核心思想**:
1. 创建 `src/reranker.py` 独立模块，封装 BGE Reranker
2. 使用单例模式，全局共享一个模型实例
3. 在 GraphRAG 的 `retrieve()` 方法中集成 Reranker 精排
4. 传统 RAG 和 GraphRAG 都使用新模块（去除重复代码）

**设计原则**:
- ✅ **代码简洁**: 直接替换，无兼容层
- ✅ **全局统一**: 所有模块使用同一 API
- ✅ **配置化集成**: 支持配置化启用/禁用
- ✅ **复用现有资源**: 不增加模型加载开销

### 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| **Reranker 模型** | BGE-reranker-v2-m3 | 复用现有模型，无需额外下载 |
| **部署方式** | 直接导入（非服务化） | 推理快（10-100ms），无并发需求 |
| **设计模式** | 单例模式 | 全局共享实例，节省内存 |
| **配置管理** | Pydantic Settings | 与现有配置体系一致 |

---

## 架构设计

### 模块依赖关系

```
传统 RAG (src/rag.py) ──┐
                        ├──→ Reranker 模块 (src/reranker.py)
GraphRAG (src/graph_rag.py) ──┘           ↓
                                    FlagReranker
                                    (BAAI/bge-reranker-v2-m3)
```

### 文件结构

```
src/
├── reranker.py          # ✅ 新增：独立的 Reranker 模块
├── rag.py               # 🔧 修改：使用 reranker 模块
├── graph_rag.py         # 🔧 修改：集成 reranker
└── config.py            # 🔧 修改：新增 GraphRAG Reranker 配置
```

### 数据流程

```
用户输入 "bwpg"
    ↓
【阶段 1】图检索
    ├─ LLMSynonymRetriever → 10 个结果
    ├─ VectorContextRetriever → 10 个结果
    └─ PGRetriever 合并 → 15 个候选
    ↓
【阶段 2】缓存检查
    ├─ 命中缓存 → 返回缓存结果
    └─ 未命中 → 继续阶段 3
    ↓
【阶段 3】Reranker 精排（新增）
    ├─ 输入：query="bwpg", candidates=[15 个结果]
    ├─ 处理：reranker.compute_score([[query, doc1], [query, doc2], ...])
    ├─ 输出：按 rerank_score 重排序
    └─ 返回：Top-3 最相关结果
    ↓
【阶段 4】更新缓存
    └─ 缓存 reranker 后的结果
    ↓
返回给 VLM
```

---

## 实现细节

### 1. 新增模块：`src/reranker.py`

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

### 2. 修改 `src/rag.py`

**删除重复代码**：

```python
# ❌ 删除 _initialize_reranker() 方法（第 105-114 行）
# ❌ 删除 _rerank_results() 方法（第 453-472 行）
```

**新增导入**：

```python
from src.reranker import get_reranker_instance
```

**修改初始化**：

```python
class RAGRetriever:
    def __init__(self):
        # ... 其他初始化

        # ✅ 获取全局 Reranker 实例
        self.reranker = get_reranker_instance()
```

**修改检索方法**：

```python
def retrieve(self, query: str) -> List[Dict[str, Any]]:
    # ... 检索逻辑

    # 选择检索模式
    if config.retrieval.mode == "hybrid" and config.retrieval.hybrid_enabled:
        results = self._retrieve_hybrid(query)
    elif config.retrieval.mode == "adaptive":
        results = self._retrieve_adaptive(query)
    else:
        results = self._retrieve_fixed(query)

    # ✅ 使用独立模块进行 Reranker 精排
    if config.rerank.enabled and self.reranker.is_enabled():
        results = self.reranker.rerank(
            query,
            results,
            top_k=config.rerank.final_top_k
        )

    return results[:config.rag.top_k]
```

### 3. 修改 `src/graph_rag.py`

**新增导入**：

```python
from src.reranker import get_reranker_instance
```

**修改初始化**：

```python
class GraphRAGRetriever:
    def __init__(self):
        # ... 其他初始化

        # ✅ 获取全局 Reranker 实例
        self.reranker_manager = get_reranker_instance()
```

**修改检索方法**：

```python
def retrieve(self, query: str) -> List[Dict[str, Any]]:
    """检索图谱（增加 Reranker 精排）"""
    if not self._initialized:
        logger.warning("GraphRAG 模块未初始化")
        return []

    if not query or not query.strip():
        return []

    start_time = time.time()

    # 检查缓存
    if config.graph_performance.query_cache_ttl > 0:
        cache_key = self._get_cache_key(query)
        if cache_key in self.query_cache:
            cached = self.query_cache[cache_key]
            if time.time() - cached['timestamp'] < config.graph_performance.query_cache_ttl:
                logger.info(f"缓存命中: {query[:50]}...")
                return cached['results']

    # 图检索
    graph_results = self._retrieve_graph(query) if self.graph_retriever else []

    # ✅ 【新增】Reranker 精排
    if config.graph_rerank.enabled and self.reranker_manager.is_enabled():
        logger.info(f"Reranker 精排前: {len(graph_results)} 个候选")
        graph_results = self.reranker_manager.rerank(
            query,
            graph_results,
            top_k=config.graph_rerank.final_top_k
        )

    # 更新缓存（缓存 reranker 后的结果）
    if config.graph_performance.query_cache_ttl > 0:
        self._update_cache(query, graph_results)

    elapsed = time.time() - start_time
    logger.info(f"GraphRAG 检索耗时: {elapsed:.3f}s")

    return graph_results[:config.rag.top_k]
```

### 4. 修改 `src/config.py`

**新增配置类**：

```python
class GraphRerankConfig(BaseAppConfig):
    """GraphRAG Reranker 配置"""
    enabled: bool = Field(default=False, alias="GRAPH_RERANK_ENABLED")
    top_k: int = Field(default=10, alias="GRAPH_RERANK_TOP_K")
    final_top_k: int = Field(default=3, alias="GRAPH_RERANK_FINAL_TOP_K")
```

**添加到全局配置**：

```python
class Config(BaseSettings):
    # ... 现有配置

    # 新增 GraphRAG Reranker 配置
    graph_rerank: GraphRerankConfig = GraphRerankConfig()
```

### 5. 配置文件 `.env`

```bash
# GraphRAG Reranker 配置
GRAPH_RERANK_ENABLED=true                    # 启用 Reranker
GRAPH_RERANK_TOP_K=10                        # 精排前保留的候选数
GRAPH_RERANK_FINAL_TOP_K=3                   # 最终返回给 VLM 的结果数

# 复用传统 RAG 的 Reranker 模型配置（已存在）
RAG_RERANK_ENABLED=true
RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3
RAG_RERANK_DEVICE=auto
```

---

## 测试策略

### 单元测试

**测试文件**: `tests/test_reranker.py`

```python
import pytest
from src.reranker import get_reranker_instance, RerankerManager

def test_reranker_singleton():
    """测试单例模式"""
    reranker1 = get_reranker_instance()
    reranker2 = get_reranker_instance()
    assert reranker1 is reranker2

def test_reranker_initialization():
    """测试初始化"""
    reranker = get_reranker_instance()
    assert reranker.is_enabled() or not reranker._initialized

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

    # 验证结果已排序
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

    assert 'enabled' in info
    assert 'initialized' in info
    assert 'model' in info
    assert 'device' in info
```

### 集成测试

**测试文件**: `tests/test_graph_rag_reranker.py`

```python
import pytest
from src.graph_rag import GraphRAGRetriever
from src.config import config

def test_graph_rag_with_reranker():
    """测试 GraphRAG + Reranker 集成"""
    # 启用 Reranker
    config.graph_rerank.enabled = True

    retriever = GraphRAGRetriever()
    assert retriever.is_enabled()

    # 测试检索
    results = retriever.retrieve("bwpg")
    assert len(results) > 0

    # 验证包含 rerank_score
    if config.graph_rerank.enabled:
        assert all('rerank_score' in r for r in results)

def test_graph_rag_without_reranker():
    """测试禁用 Reranker 的情况"""
    # 禁用 Reranker
    config.graph_rerank.enabled = False

    retriever = GraphRAGRetriever()
    results = retriever.retrieve("bwpg")

    # 验证不包含 rerank_score
    assert not any('rerank_score' in r for r in results)

def test_reranker_abbreviation_matching():
    """测试缩写识别准确率"""
    config.graph_rerank.enabled = True

    retriever = GraphRAGRetriever()

    test_cases = [
        ("bwpg", "斗轮驱动行星减速机"),
        ("bcdp", "皮带机驱动滚筒"),
        ("bcbp", "皮带机改向滚筒"),
    ]

    for query, expected_part in test_cases:
        results = retriever.retrieve(query)

        # 验证第一个结果包含期望的部件名称
        if results:
            assert expected_part in results[0]['text']

def test_performance_latency():
    """测试性能延迟"""
    import time

    config.graph_rerank.enabled = True
    retriever = GraphRAGRetriever()

    start = time.time()
    results = retriever.retrieve("bwpg")
    elapsed = time.time() - start

    # 验证延迟在可接受范围内（< 500ms）
    assert elapsed < 0.5
```

### 性能测试

**测试脚本**: `tests/benchmark_reranker.py`

```python
import time
from src.reranker import get_reranker_instance

def benchmark_reranker_latency():
    """基准测试：Reranker 延迟"""
    reranker = get_reranker_instance()

    query = "bwpg"
    results = [
        {'text': f'测试结果 {i}'}
        for i in range(10)
    ]

    # 预热
    reranker.rerank(query, results)

    # 正式测试
    latencies = []
    for _ in range(100):
        start = time.time()
        reranker.rerank(query, results)
        latencies.append(time.time() - start)

    avg_latency = sum(latencies) / len(latencies)
    p95_latency = sorted(latencies)[94]  # 95th percentile

    print(f"平均延迟: {avg_latency*1000:.2f}ms")
    print(f"P95 延迟: {p95_latency*1000:.2f}ms")

    # 验证性能要求
    assert avg_latency < 0.2  # 平均 < 200ms
    assert p95_latency < 0.5  # P95 < 500ms

if __name__ == "__main__":
    benchmark_reranker_latency()
```

---

## 风险评估

### 技术风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| **FlagEmbedding 库未安装** | 中 | 高 | 自动降级，禁用 Reranker |
| **GPU 内存不足** | 低 | 中 | 自动回退到 CPU |
| **Reranker 推理失败** | 低 | 低 | 捕获异常，返回原始结果 |
| **性能不达标** | 低 | 中 | 可配置禁用，影响可控 |

### 兼容性风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| **API 变化需要更新调用方** | 中 | 低 | 统一修改所有使用的地方 |
| **配置冲突** | 低 | 低 | 独立的配置命名空间 |

### 运维风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| **模型加载时间增加** | 低 | 低 | 延迟初始化，按需加载 |
| **调试难度增加** | 低 | 低 | 详细的日志记录 |

---

## 实施计划

### 阶段 1：独立模块开发（1-2 天）

**任务**:
- [ ] 创建 `src/reranker.py`
- [ ] 实现 `RerankerManager` 类
- [ ] 实现单例模式
- [ ] 实现错误处理和降级策略
- [ ] 编写单元测试

**验收标准**:
- 单元测试通过
- 能成功初始化 Reranker
- 能正确执行重排序

### 阶段 2：GraphRAG 集成（0.5-1 天）

**任务**:
- [ ] 修改 `src/graph_rag.py`
- [ ] 集成 Reranker 精排
- [ ] 添加配置项
- [ ] 编写集成测试

**验收标准**:
- 集成测试通过
- 缩写识别率提升
- 性能延迟 < 500ms

### 阶段 3：传统 RAG 重构（0.5 天）

**任务**:
- [ ] 修改 `src/rag.py`
- [ ] 删除重复代码
- [ ] 使用独立模块
- [ ] 回归测试

**验收标准**:
- 传统 RAG 功能不受影响
- 代码重复率降低

### 阶段 4：文档与部署（0.5 天）

**任务**:
- [ ] 更新 `.env.example`
- [ ] 更新 `CLAUDE.md`
- [ ] 编写使用说明
- [ ] 性能测试与调优

**验收标准**:
- 文档完整
- 性能达标

### 总计：2.5-4 天

---

## 预期效果

### 准确性提升

| 测试用例 | 当前（无 Reranker） | 预期（有 Reranker） |
|---------|-------------------|-------------------|
| **bwpg** | 部分字段缺失 | ✅ 完整字段 |
| **bcdp** | 字段全为 null | ✅ 完整字段 |
| **sdpg** | 只有缩写 | ✅ 完整中文名称 |
| **溜槽耐磨板** | 部分 null | ✅ 准确匹配 |

### 性能影响

| 指标 | 当前 | 预期 |
|------|------|------|
| **GraphRAG 检索延迟** | ~30-40ms | ~80-150ms |
| **额外延迟** | 0 | +50-100ms |
| **内存占用** | 基准 | +400MB（共享） |
| **代码重复** | 2 处 | 0 处 |

### 代码质量

| 指标 | 当前 | 预期 |
|------|------|------|
| **代码重复行数** | ~70 行 | 0 行 |
| **可维护性** | 中 | 高 |
| **测试覆盖率** | 低 | 高 |

---

## 附录

### A. 相关文档

- [BGE Reranker 官方文档](https://github.com/FlagOpen/FlagEmbedding)
- [LlamaIndex Property Graph Index 指南](https://docs.llamaindex.ai/en/stable/module_guides/indexing/lpg_index_guide/)
- [项目 CLAUDE.md](/home/catlab/wh/wh_graphrag_re/CLAUDE.md)

### B. 配置参考

```bash
# .env 完整配置示例

# Reranker 全局配置（传统 RAG 和 GraphRAG 共享）
RAG_RERANK_ENABLED=true
RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3
RAG_RERANK_DEVICE=auto
RAG_RERANK_TOP_K=10
RAG_RERANK_FINAL_TOP_K=3

# GraphRAG Reranker 配置
GRAPH_RERANK_ENABLED=true
GRAPH_RERANK_TOP_K=10
GRAPH_RERANK_FINAL_TOP_K=3

# GraphRAG 检索配置
GRAPH_RETRIEVAL_SUB_RETRIEVERS=vector,synonym
GRAPH_RETRIEVAL_VECTOR_TOP_K=10
GRAPH_RETRIEVAL_VECTOR_PATH_DEPTH=2
GRAPH_RETRIEVAL_SYNONYM_MAX_KEYWORDS=15
GRAPH_RETRIEVAL_SYNONYM_PATH_DEPTH=2
```

### C. 故障排查

**问题 1**: Reranker 初始化失败

```
错误信息: FlagEmbedding 库未安装
解决方法: pip install -U FlagEmbedding
```

**问题 2**: GPU 内存不足

```
错误信息: CUDA out of memory
解决方法: 设置 RAG_RERANK_DEVICE=cpu
```

**问题 3**: 性能延迟过大

```
检查方法:
1. 查看 GRAPH_RERANK_TOP_K 是否过大（建议 10）
2. 检查 GPU 利用率
3. 查看 Reranker 日志中的耗时
```

---

## 审批意见

**请审阅以上设计方案，并提供反馈：**

1. ✅ 同意实施
2. ⚠️ 需要修改（请说明具体问题）
3. ❌ 不同意实施（请说明原因）

---

**文档版本**: v1.0
**最后更新**: 2026-03-27
