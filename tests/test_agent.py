import json
from unittest.mock import patch, MagicMock


def test_query_knowledge_base_returns_json():
    mock_results = ["深沟球轴承用于高速旋转场景", "型号6208-2RS常用于港口设备"]
    mock_manager = MagicMock()
    mock_manager.retrieve.return_value = [{"text": r} for r in mock_results]
    mock_manager.mode = "traditional"

    with patch("src.agents.instruction.tools.get_unified_rag_manager", return_value=mock_manager):
        from src.agents.instruction.tools import query_knowledge_base
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
    mock_db = MagicMock()
    mock_db.query.return_value = mock_item
    mock_db.query_by_name.return_value = None

    with patch("src.agents.inventory.tools._get_stock_manager", return_value=mock_db):
        from src.agents.inventory.tools import query_inventory
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
    mock_db = MagicMock()
    mock_db.query.return_value = mock_item
    mock_db.query_by_name.return_value = None

    with patch("src.agents.inventory.tools._get_stock_manager", return_value=mock_db):
        from src.agents.inventory.tools import query_inventory
        result = query_inventory.invoke({
            "model": "6208-2RS-C3-SKF-Mech1",
            "part_name": "深沟球轴承",
            "quantity": 5,
        })

    data = json.loads(result)
    assert data["available"] == 1
    assert data["sufficient"] is False


def test_create_restock_returns_order_id():
    """create_restock 是普通函数，直接调用并断言返回结构。"""
    mock_map_cfg = MagicMock()

    with patch("src.agents.inventory.tools.MapRegistry") as MockRegistry, \
         patch("src.agents.inventory.tools.OrderManager") as MockOM:
        MockRegistry.get.return_value = mock_map_cfg
        MockOM.return_value.from_port_instruction.return_value = MagicMock()

        from src.agents.inventory.tools import create_restock
        result = create_restock(
            model="6208-2RS-C3-SKF-Mech1",
            part_name="深沟球轴承",
            shortage=4,
            is_urgent=False,
        )

    assert result["status"] == "created"
    assert "order_id" in result
    assert result["order_id"].startswith("RS-")
    assert "4" in result["message"]

