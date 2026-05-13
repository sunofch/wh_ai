import json
from langchain_core.tools import tool
from src.rag import get_unified_rag_manager


@tool
def query_knowledge_base(query: str, top_k: int = 3) -> str:
    """当备件名称或型号不明确时调用，从知识库检索相关信息。"""
    try:
        manager = get_unified_rag_manager()
        nodes = manager.retrieve(query)
        context = manager.format_context(nodes) if nodes else ""
        results = [line for line in context.split("\n") if line.strip()][:top_k]
        source = "traditional"
    except Exception as e:
        results = []
        source = f"error: {e}"

    return json.dumps({"results": results, "source": source}, ensure_ascii=False)
