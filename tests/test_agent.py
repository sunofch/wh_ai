import json
from unittest.mock import patch, MagicMock


def test_query_knowledge_base_returns_json():
    mock_results = ["深沟球轴承用于高速旋转场景", "型号6208-2RS常用于港口设备"]
    mock_manager = MagicMock()
    mock_manager.retrieve.return_value = [MagicMock(get_content=lambda: r) for r in mock_results]
    mock_manager.format_context.return_value = "\n".join(mock_results)

    with patch("src.agent.tools.knowledge_tool.get_unified_rag_manager", return_value=mock_manager):
        from src.agent.tools.knowledge_tool import query_knowledge_base
        result = query_knowledge_base.invoke({"query": "轴承", "top_k": 2})

    data = json.loads(result)
    assert "results" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) > 0
