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


def test_create_restock_order_returns_order_id():
    from src.warehouse.models import WorkOrder, OrderItem, TaskType, OrderPriority
    mock_order = WorkOrder(
        order_id=1,
        source="vlm",
        priority=OrderPriority.NORMAL,
        items=[OrderItem(item_id=1, task_type=TaskType.INBOUND, quantity=4)],
    )
    with patch("src.agent.tools.order_tool.OrderManager") as MockOM:
        MockOM.return_value.from_port_instruction.return_value = mock_order

        from src.agent.tools.order_tool import create_restock_order
        result = create_restock_order.invoke({
            "model": "6208-2RS-C3-SKF-Mech1",
            "part_name": "深沟球轴承",
            "shortage": 4,
            "is_urgent": False,
        })

    data = json.loads(result)
    assert data["status"] == "created"
    assert "order_id" in data
    assert "4" in data["message"]


# ── Agent 三条路径测试 ────────────────────────────────────────────────────────

def _make_agent_response(fields: dict, tool_calls_log: list | None = None):
    """构造 Agent invoke() 返回的 messages 结构。"""
    from langchain_core.messages import AIMessage, ToolMessage
    import json as _json

    msgs = []
    for tc in (tool_calls_log or []):
        msgs.append(ToolMessage(content=tc, tool_call_id="mock", name="mock"))
    msgs.append(AIMessage(content=_json.dumps(fields, ensure_ascii=False)))
    return {"messages": msgs}


def test_run_agent_complete_fields_sufficient_inventory():
    """路径1：字段完整 + 库存充足 → WorkOrder，不触发补货"""
    from src.warehouse.models import InventoryItem, WorkOrder, OrderItem, TaskType, OrderPriority

    mock_item = InventoryItem(
        model="6208-Mech1", part_name="深沟球轴承",
        quantity=10, reserved=0, available=10,
        location="Mech1_R1_B1", zone="Mech1",
    )
    mock_order = WorkOrder(
        order_id=1, source="vlm", priority=OrderPriority.NORMAL,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=5,
                         resolved_pick="Mech1_R1_B1", resolved_dest="PORT_OUT_1")],
    )
    agent_resp = _make_agent_response({
        "part_name": "深沟球轴承", "quantity": 5,
        "model": "6208-Mech1", "action_required": "出库", "is_urgent": False,
    })

    with patch("src.agent.agent._get_compiled_agent") as mock_ag, \
         patch("src.agent.agent.StockManager") as MockDB, \
         patch("src.agent.agent.OrderManager") as MockOM:
        mock_ag.return_value.invoke.return_value = agent_resp
        MockDB.return_value.query.return_value = mock_item
        MockDB.return_value.query_by_name.return_value = None
        MockOM.return_value.from_port_instruction.return_value = mock_order

        from src.agent.agent import run_agent
        order = run_agent(text="需要5个深沟球轴承出库")

    assert isinstance(order, WorkOrder)
    assert order.items[0].resolved_pick == "Mech1_R1_B1"
    assert "restock_order_id" not in order.metadata


def test_run_agent_missing_part_name_calls_kb():
    """路径2：part_name 缺失 → Agent 调用知识库补全"""
    from src.warehouse.models import InventoryItem, WorkOrder, OrderItem, TaskType, OrderPriority

    mock_item = InventoryItem(
        model="6208-Mech1", part_name="深沟球轴承",
        quantity=10, reserved=0, available=10,
        location="Mech1_R1_B1", zone="Mech1",
    )
    mock_order = WorkOrder(
        order_id=1, source="vlm", priority=OrderPriority.NORMAL,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=3)],
    )
    kb_tool_result = json.dumps({"results": ["深沟球轴承用于高速旋转"], "source": "traditional"})
    agent_resp = _make_agent_response(
        {"part_name": "深沟球轴承", "quantity": 3,
         "model": "6208-Mech1", "action_required": "出库", "is_urgent": False},
        tool_calls_log=[kb_tool_result],
    )

    with patch("src.agent.agent._get_compiled_agent") as mock_ag, \
         patch("src.agent.agent.StockManager") as MockDB, \
         patch("src.agent.agent.OrderManager") as MockOM:
        mock_ag.return_value.invoke.return_value = agent_resp
        MockDB.return_value.query.return_value = mock_item
        MockOM.return_value.from_port_instruction.return_value = mock_order

        from src.agent.agent import run_agent
        order = run_agent(text="需要3个轴承")

    assert isinstance(order, WorkOrder)
    assert order.items[0].quantity == 3


def test_run_agent_insufficient_inventory_creates_restock():
    """路径3：库存不足（出库）→ metadata 含 restock_order_id"""
    from src.warehouse.models import InventoryItem, WorkOrder, OrderItem, TaskType, OrderPriority

    mock_item = InventoryItem(
        model="6208-Mech1", part_name="深沟球轴承",
        quantity=2, reserved=0, available=2,
        location="Mech1_R1_B1", zone="Mech1",
    )
    mock_order = WorkOrder(
        order_id=1, source="vlm", priority=OrderPriority.NORMAL,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=5)],
    )
    restock_tool_result = json.dumps({
        "order_id": "RS-ABCD1234", "status": "created", "message": "缺口数量: 3"
    })
    agent_resp = _make_agent_response(
        {"part_name": "深沟球轴承", "quantity": 5,
         "model": "6208-Mech1", "action_required": "出库", "is_urgent": False},
        tool_calls_log=[restock_tool_result],
    )

    with patch("src.agent.agent._get_compiled_agent") as mock_ag, \
         patch("src.agent.agent.StockManager") as MockDB, \
         patch("src.agent.agent.OrderManager") as MockOM:
        mock_ag.return_value.invoke.return_value = agent_resp
        MockDB.return_value.query.return_value = mock_item
        MockOM.return_value.from_port_instruction.return_value = mock_order

        from src.agent.agent import run_agent
        order = run_agent(text="需要5个深沟球轴承出库")

    assert isinstance(order, WorkOrder)
    assert order.metadata.get("restock_order_id") == "RS-ABCD1234"
