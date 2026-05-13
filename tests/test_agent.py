import json
from unittest.mock import patch, MagicMock, PropertyMock


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


def test_query_inventory_sufficient():
    from src.warehouse.models import InventoryItem
    mock_item = InventoryItem(
        model="6208-2RS-C3-SKF-Mech1",
        part_name="深沟球轴承",
        quantity=10,
        reserved=2,
        available=8,
        location="Mech1_R1_B1",
        zone="Mech1",
    )
    with patch("src.agent.tools.inventory_tool.StockManager") as MockDB:
        MockDB.return_value.query.return_value = mock_item
        MockDB.return_value.query_by_name.return_value = None

        from src.agent.tools.inventory_tool import query_inventory
        result = query_inventory.invoke({
            "model": "6208-2RS-C3-SKF-Mech1",
            "part_name": "深沟球轴承",
            "quantity": 5,
        })

    data = json.loads(result)
    assert data["available"] == 8
    assert data["sufficient"] is True
    assert data["location"] == "Mech1_R1_B1"


def test_query_inventory_insufficient():
    from src.warehouse.models import InventoryItem
    mock_item = InventoryItem(
        model="6208-2RS-C3-SKF-Mech1",
        part_name="深沟球轴承",
        quantity=2,
        reserved=1,
        available=1,
        location="Mech1_R1_B1",
        zone="Mech1",
    )
    with patch("src.agent.tools.inventory_tool.StockManager") as MockDB:
        MockDB.return_value.query.return_value = mock_item
        MockDB.return_value.query_by_name.return_value = None

        from src.agent.tools.inventory_tool import query_inventory
        result = query_inventory.invoke({
            "model": "6208-2RS-C3-SKF-Mech1",
            "part_name": "深沟球轴承",
            "quantity": 5,
        })

    data = json.loads(result)
    assert data["available"] == 1
    assert data["sufficient"] is False
