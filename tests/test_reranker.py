"""
Reranker 模块单元测试
"""
import pytest
from src.common.reranker import get_reranker_instance, RerankerManager, rerank_results


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
