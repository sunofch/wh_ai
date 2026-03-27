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

from .config import config
from .utils import get_device

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
