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
