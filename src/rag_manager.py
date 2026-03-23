"""
统一RAG管理器
支持传统RAG和GraphRAG的独立模式
"""

import logging
from typing import Optional, Union, Dict, Any
from src.rag import get_rag_instance, RAGRetriever
from src.graph_rag import get_graph_rag_instance, GraphRAGRetriever, check_graph_rag_available

logger = logging.getLogger(__name__)

class UnifiedRAGManager:
    """统一的RAG管理器，支持传统RAG和GraphRAG模式"""

    def __init__(self):
        self.traditional_rag: Optional[RAGRetriever] = None
        self.graph_rag: Optional[GraphRAGRetriever] = None
        self.mode = 'traditional'  # 'traditional' | 'graph'
        self.enabled = False
        self.last_error = None

    def initialize(self, mode: str = 'traditional') -> bool:
        """
        初始化RAG系统

        Args:
            mode: 模式选择 ('traditional' | 'graph')

        Returns:
            bool: 初始化成功返回True，否则False
        """
        if mode not in ['traditional', 'graph']:
            self.last_error = f"无效的模式: {mode}"
            return False

        self.mode = mode
        self.last_error = None

        try:
            if mode == 'graph':
                # GraphRAG模式
                if not check_graph_rag_available():
                    self.enabled = False
                    self.last_error = "GraphRAG不可用"
                    logger.warning("GraphRAG不可用，请检查配置")
                    return False

                self.traditional_rag = None  # 清空传统RAG
                self.graph_rag = get_graph_rag_instance()
                if self.graph_rag and self.graph_rag.is_enabled():
                    self.enabled = True
                    logger.info("GraphRAG初始化成功")
                    return True
                else:
                    self.enabled = False
                    self.last_error = "GraphRAG初始化失败"
                    return False

            else:
                # 传统RAG模式
                self.graph_rag = None  # 清空GraphRAG
                self.traditional_rag = get_rag_instance()
                if self.traditional_rag:
                    self.enabled = True
                    logger.info("传统RAG初始化成功")
                    return True
                else:
                    self.enabled = False
                    self.last_error = "传统RAG初始化失败"
                    return False

        except Exception as e:
            self.enabled = False
            self.last_error = str(e)
            logger.error(f"RAG初始化失败: {e}")
            return False

    def get_retriever(self) -> Optional[Union[RAGRetriever, GraphRAGRetriever]]:
        """
        获取当前模式的retriever

        Returns:
            retriever对象或None
        """
        if not self.enabled:
            return None

        if self.mode == 'graph':
            return self.graph_rag
        else:
            return self.traditional_rag

    def set_enabled(self, enabled: bool):
        """启用/禁用RAG"""
        self.enabled = enabled
        if not enabled:
            self.last_error = None

    def get_status(self) -> Dict[str, Any]:
        """
        获取RAG状态信息

        Returns:
            包含详细状态信息的字典
        """
        status = {
            'enabled': self.enabled,
            'mode': self.mode,
            'available': False,
            'last_error': self.last_error
        }

        retriever = self.get_retriever()
        if retriever:
            status['available'] = True

            if self.mode == 'graph' and isinstance(retriever, GraphRAGRetriever):
                # GraphRAG状态
                status['type'] = 'graph'

                # 添加GraphRAG特有的状态信息
                if hasattr(retriever, 'config'):
                    status['extractor_type'] = retriever.config.extractor_type
                    status['max_triplets_per_chunk'] = retriever.config.max_triplets_per_chunk
                    status['entity_hints'] = retriever.config.entity_hints

            elif isinstance(retriever, RAGRetriever):
                # 传统RAG状态
                status['type'] = 'traditional'
                if hasattr(retriever, 'retriever'):
                    status['top_k'] = getattr(retriever.retriever, 'similarity_top_k', 3)
                    status['retrieval_mode'] = getattr(retriever, 'retrieval_mode', 'hybrid')
                if hasattr(retriever, 'get_status'):
                    status.update(retriever.get_status())

        return status

    def retrieve(self, query: str, top_k: Optional[int] = None) -> list:
        """
        执行检索

        Args:
            query: 查询文本
            top_k: 返回结果数量，None表示使用配置默认值

        Returns:
            检索结果列表
        """
        if not self.enabled:
            return []

        retriever = self.get_retriever()
        if not retriever:
            return []

        try:
            # 对于传统RAG，可以动态指定top_k
            if isinstance(retriever, RAGRetriever) and top_k:
                # 保存原始top_k
                original_top_k = getattr(retriever.retriever, 'similarity_top_k', None)
                # 临时设置新的top_k
                if hasattr(retriever.retriever, 'similarity_top_k'):
                    retriever.retriever.similarity_top_k = top_k

                # 执行检索
                results = retriever.retrieve(query)

                # 恢复原始top_k
                if original_top_k is not None:
                    retriever.retriever.similarity_top_k = original_top_k

                return results
            else:
                return retriever.retrieve(query)

        except Exception as e:
            logger.error(f"RAG检索失败: {e}")
            self.last_error = str(e)
            return []

    def rebuild_index(self) -> bool:
        """
        重建索引

        Returns:
            bool: 重建成功返回True，否则False
        """
        if not self.enabled:
            return False

        retriever = self.get_retriever()
        if not retriever:
            return False

        try:
            if hasattr(retriever, 'rebuild_index'):
                retriever.rebuild_index()
                return True
            return False
        except Exception as e:
            logger.error(f"重建索引失败: {e}")
            self.last_error = str(e)
            return False

    def format_context(self, results: list) -> str:
        """
        格式化检索结果为上下文

        Args:
            results: 检索结果列表

        Returns:
            格式化后的上下文字符串
        """
        if not self.enabled or not results:
            return ""

        retriever = self.get_retriever()
        if not retriever:
            return ""

        try:
            if hasattr(retriever, 'format_context'):
                return retriever.format_context(results)
            elif hasattr(retriever, 'get_formatted_context'):
                return retriever.get_formatted_context(results)
            else:
                # 默认格式化
                context = "相关文档信息：\n"
                for i, result in enumerate(results, 1):
                    if isinstance(result, dict):
                        score = result.get('score', 0)
                        text = result.get('text', '')
                        context += f"{i}. [{score:.3f}] {text}\n"
                return context
        except Exception as e:
            logger.error(f"格式化上下文失败: {e}")
            self.last_error = str(e)
            return ""

    @property
    def is_traditional_mode(self) -> bool:
        """是否为传统RAG模式"""
        return self.mode == 'traditional'

    @property
    def is_graph_mode(self) -> bool:
        """是否为GraphRAG模式"""
        return self.mode == 'graph'

    def clear_cache(self):
        """清除查询缓存（仅对GraphRAG有效）"""
        if self.is_graph_mode and self.graph_rag:
            if hasattr(self.graph_rag, 'clear_query_cache'):
                self.graph_rag.clear_query_cache()
            elif hasattr(self.graph_rag, 'retriever') and hasattr(self.graph_rag.retriever, 'clear_cache'):
                self.graph_rag.retriever.clear_cache()


# 全局RAG管理器实例
_global_rag_manager: Optional[UnifiedRAGManager] = None

def get_unified_rag_manager() -> UnifiedRAGManager:
    """
    获取全局RAG管理器实例（单例模式）

    Returns:
        UnifiedRAGManager实例
    """
    global _global_rag_manager
    if _global_rag_manager is None:
        _global_rag_manager = UnifiedRAGManager()
    return _global_rag_manager

def initialize_rag_system(mode: str = 'traditional') -> bool:
    """
    初始化全局RAG系统

    Args:
        mode: 模式选择 ('traditional' | 'graph')

    Returns:
        bool: 初始化成功返回True，否则False
    """
    manager = get_unified_rag_manager()
    return manager.initialize(mode=mode)

def get_rag_retriever() -> Optional[Union[RAGRetriever, GraphRAGRetriever]]:
    """
    获取当前RAG retriever

    Returns:
        retriever对象或None
    """
    manager = get_unified_rag_manager()
    return manager.get_retriever()