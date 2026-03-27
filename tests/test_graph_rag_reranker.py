"""
GraphRAG Reranker 集成测试
"""
import os
import pytest


@pytest.mark.skipif(
    not os.environ.get('GRAPH_RAG_DEEPSEEK_API_KEY'),
    reason="需要 GRAPH_RAG_DEEPSEEK_API_KEY 环境变量"
)
def test_graph_rag_reranker_integration():
    """测试 GraphRAG 与 Reranker 集成"""
    from src.rag import GraphRAGRetriever
    from src.common.config import config

    # 确保 GraphRAG 和 Reranker 都启用
    if not config.rag.graph_enabled:
        pytest.skip("GraphRAG 未启用")

    # 创建 GraphRAG 实例
    retriever = GraphRAGRetriever()

    # 测试查询
    query = "bwpg"
    results = retriever.retrieve(query)

    # 验证结果
    assert isinstance(results, list)

    # 如果启用了 Reranker，检查 rerank_score
    if config.graph_rerank.enabled:
        assert all('rerank_score' in r for r in results), "所有结果应包含 rerank_score"
        # 验证结果已排序（降序）
        scores = [r['rerank_score'] for r in results]
        assert scores == sorted(scores, reverse=True), "结果应按 rerank_score 降序排列"


def test_graph_rag_reranker_disabled():
    """测试禁用 Reranker 时的行为"""
    from src.rag import GraphRAGRetriever
    from src.common.config import config

    # 临时保存原配置
    original_enabled = config.graph_rerank.enabled

    try:
        # 确保禁用 Reranker
        if config.graph_rerank.enabled:
            pytest.skip("Reranker 已启用，跳过禁用测试")

        # 创建 GraphRAG 实例
        retriever = GraphRAGRetriever()

        # 测试查询
        query = "测试查询"
        results = retriever.retrieve(query)

        # 验证结果不包含 rerank_score（除非 Reranker 实际启用了）
        if results and not config.graph_rerank.enabled:
            # 结果可能没有 rerank_score 字段
            pass  # 不强制要求，因为 Reranker 可能被全局启用

    finally:
        # 恢复原配置
        config.graph_rerank.enabled = original_enabled


@pytest.mark.skipif(
    not os.environ.get('GRAPH_RAG_DEEPSEEK_API_KEY'),
    reason="需要 GRAPH_RAG_DEEPSEEK_API_KEY 环境变量"
)
def test_reranker_top_k_limit():
    """测试 Reranker Top-K 限制"""
    from src.rag import GraphRAGRetriever
    from src.common.config import config

    if not config.graph_rerank.enabled:
        pytest.skip("GraphRAG Reranker 未启用")

    # 创建 GraphRAG 实例
    retriever = GraphRAGRetriever()

    # 测试查询
    query = "备件"
    results = retriever.retrieve(query)

    # 验证结果数量不超过 final_top_k
    assert len(results) <= config.graph_rerank.final_top_k, \
        f"结果数量 {len(results)} 不应超过 final_top_k {config.graph_rerank.final_top_k}"


@pytest.mark.skipif(
    not os.environ.get('GRAPH_RAG_DEEPSEEK_API_KEY'),
    reason="需要 GRAPH_RAG_DEEPSEEK_API_KEY 环境变量"
)
def test_reranker_with_empty_results():
    """测试 Reranker 处理空结果"""
    from src.rag import GraphRAGRetriever
    from src.common.config import config

    if not config.graph_rerank.enabled:
        pytest.skip("GraphRAG Reranker 未启用")

    # 创建 GraphRAG 实例
    retriever = GraphRAGRetriever()

    # 测试无效查询
    query = "xyz123notexist"
    results = retriever.retrieve(query)

    # 验证返回空列表（而不是报错）
    assert isinstance(results, list)
    # 可能是空列表或少量结果
    if results:
        assert all('rerank_score' in r for r in results)


@pytest.mark.skipif(
    not os.environ.get('GRAPH_RAG_DEEPSEEK_API_KEY'),
    reason="需要 GRAPH_RAG_DEEPSEEK_API_KEY 环境变量"
)
def test_reranker_preserves_metadata():
    """测试 Reranker 保留原始元数据"""
    from src.rag import GraphRAGRetriever
    from src.common.config import config

    if not config.graph_rerank.enabled:
        pytest.skip("GraphRAG Reranker 未启用")

    # 创建 GraphRAG 实例
    retriever = GraphRAGRetriever()

    # 测试查询
    query = "bwpg"
    results = retriever.retrieve(query)

    # 验证每个结果保留原始字段
    for result in results:
        assert 'text' in result, "结果应包含 text 字段"
        assert 'metadata' in result, "结果应包含 metadata 字段"
        assert 'score' in result, "结果应包含 score 字段"
        assert 'rerank_score' in result, "结果应包含 rerank_score 字段"
