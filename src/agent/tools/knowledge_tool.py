import json
from langchain_core.tools import tool
from src.rag import get_unified_rag_manager, initialize_rag_system
from src.common.config import config


def _ensure_rag_initialized():
    manager = get_unified_rag_manager()
    if not manager.enabled:
        mode = "graph" if config.rag.graph_enabled else "traditional"
        initialize_rag_system(mode=mode)
    return manager


@tool
def query_knowledge_base(query: str, top_k: int = 3) -> str:
    """当备件名称或型号不明确时调用，从知识库检索相关信息。"""
    try:
        manager = _ensure_rag_initialized()
        nodes = manager.retrieve(query, top_k=top_k)
        results = [n.get("text", "") for n in nodes if n.get("text")]
        source = manager.mode
    except Exception as e:
        results = []
        source = f"error: {e}"

    return json.dumps({"results": results, "source": source}, ensure_ascii=False)
