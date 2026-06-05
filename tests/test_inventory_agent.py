"""Inventory Management Agent 测试。

测试范围：
1. create_work_order 工具创建工单
2. create_restock_order 工具创建补货单
3. inventory_agent 名称常量正确
4. get_inventory_agent() 返回纯 Python pipeline
5. 库存不足时 pipeline 返回带补货单号的 WorkOrder
"""
import json
from unittest.mock import patch, MagicMock


# ── 1. create_work_order 工具 ────────────────────────────────────────────────

def test_create_work_order_returns_created():
    from src.warehouse.models import WorkOrder, OrderItem, TaskType, OrderPriority

    mock_order = WorkOrder(
        order_id=1, source="vlm", priority=OrderPriority.NORMAL,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND,
                         quantity=3, resolved_pick="Mech1_R1_B1", resolved_dest="PORT_OUT_1")],
    )
    # StockManager 在函数体内 import，需 patch 源模块路径
    with patch("src.agents.inventory.tools.OrderManager") as MockOM, \
         patch("src.agents.inventory.tools.MapRegistry") as MockReg, \
         patch("src.warehouse.wms.inventory_db.StockManager"):
        MockReg.get.return_value = MagicMock()
        MockOM.return_value.from_port_instruction.return_value = mock_order

        from src.agents.inventory.tools import create_work_order
        result = create_work_order.invoke({
            "part_name": "深沟球轴承", "model": "6208-Mech1",
            "quantity": 3, "action_required": "出库",
        })

    data = json.loads(result)
    assert data["status"] == "created"
    assert "items" in data
    assert data["items"][0]["quantity"] == 3


def test_create_work_order_returns_failed_when_none():
    with patch("src.agents.inventory.tools.OrderManager") as MockOM, \
         patch("src.agents.inventory.tools.MapRegistry") as MockReg, \
         patch("src.warehouse.wms.inventory_db.StockManager"):
        MockReg.get.return_value = MagicMock()
        MockOM.return_value.from_port_instruction.return_value = None

        from src.agents.inventory.tools import create_work_order
        result = create_work_order.invoke({
            "part_name": "", "model": "", "quantity": 0, "action_required": "",
        })

    data = json.loads(result)
    assert data["status"] == "failed"


# ── 2. create_restock_order 工具 ──────────────────────────────────────────────

def test_create_restock_order_returns_order_id():
    with patch("src.agents.inventory.tools.MapRegistry") as MockReg, \
         patch("src.agents.inventory.tools.OrderManager") as MockOM:
        MockReg.get.return_value = MagicMock()
        MockOM.return_value.from_port_instruction.return_value = MagicMock()

        from src.agents.inventory.tools import create_restock_order
        result = create_restock_order.invoke({
            "model": "6208-Mech1", "part_name": "深沟球轴承",
            "shortage": 3, "is_urgent": False,
        })

    data = json.loads(result)
    assert data["status"] == "created"
    assert data["order_id"].startswith("RS-")
    assert "3" in data["message"]


# ── 3. inventory_agent 名称常量 ───────────────────────────────────────────────

def test_inventory_agent_name_constant():
    from src.agents.inventory.agent import AGENT_NAME
    assert AGENT_NAME == "inventory_agent"


# ── 4. get_inventory_agent 返回 pipeline ──────────────────────────────────────

def test_get_inventory_agent_returns_pipeline():
    from src.agents.inventory.agent import get_inventory_agent
    get_inventory_agent.cache_clear()
    agent = get_inventory_agent()

    assert hasattr(agent, "run")


# ── 5. inventory_agent 库存不足时返回带补货单号的 WorkOrder ────────────────────

def test_inventory_agent_run_with_restock():
    """库存不足时，inventory_agent 调用 create_restock_order 并写入 metadata。"""
    from src.agents.inventory.agent import get_inventory_agent
    from src.warehouse.models import WorkOrder

    get_inventory_agent.cache_clear()
    inventory_result = {"available": 2, "location": "Mech1_R1_B1", "sufficient": False, "shortage": 3}
    work_order_result = {
        "status": "created",
        "order_id": 1,
        "priority": "NORMAL",
        "metadata": {},
        "items": [{
            "task_type": "OUTBOUND",
            "model": "6208-Mech1",
            "part_name": "深沟球轴承",
            "quantity": 5,
            "pick": "Mech1_R1_B1",
            "dest": "PORT_OUT_1",
        }],
    }
    restock_result = {"order_id": "RS-TEST1234", "status": "created"}

    with patch("src.agents.inventory.agent.query_inventory") as mock_query, \
         patch("src.agents.inventory.agent.create_work_order") as mock_work_order, \
         patch("src.agents.inventory.agent.create_restock_order") as mock_restock:
        mock_query.invoke.return_value = json.dumps(inventory_result, ensure_ascii=False)
        mock_work_order.invoke.return_value = json.dumps(work_order_result, ensure_ascii=False)
        mock_restock.invoke.return_value = json.dumps(restock_result, ensure_ascii=False)

        order = get_inventory_agent().run(json.dumps({
            "part_name": "深沟球轴承", "quantity": 5,
            "model": "6208-Mech1", "action_required": "出库", "is_urgent": False,
        }, ensure_ascii=False))

    assert isinstance(order, WorkOrder)
    assert order.metadata.get("restock_order_id") == "RS-TEST1234"
    mock_restock.invoke.assert_called_once()


# ── 6. _merge_work_orders 合并逻辑（自 supervisor 迁入本域）────────────────────

def test_merge_work_orders_empty():
    """_merge_work_orders 空列表返回默认 WorkOrder。"""
    from src.agents.inventory.agent import _merge_work_orders
    from src.warehouse.models import WorkOrder, OrderPriority
    result = _merge_work_orders([])
    assert isinstance(result, WorkOrder)
    assert result.priority == OrderPriority.NORMAL
    assert result.items == []


def test_merge_work_orders_single():
    """_merge_work_orders 单个 WorkOrder 原样返回。"""
    from src.agents.inventory.agent import _merge_work_orders
    from src.warehouse.models import WorkOrder, OrderPriority
    order = WorkOrder(order_id=1, source="vlm", priority=OrderPriority.NORMAL)
    result = _merge_work_orders([order])
    assert result is order


def test_merge_work_orders_multiple():
    """_merge_work_orders 多个 WorkOrder 取最高优先级，合并 items 并重新编号。"""
    from src.agents.inventory.agent import _merge_work_orders
    from src.warehouse.models import WorkOrder, OrderItem, TaskType, OrderPriority
    o1 = WorkOrder(
        order_id=1, source="vlm", priority=OrderPriority.NORMAL,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=1)],
    )
    o2 = WorkOrder(
        order_id=2, source="vlm", priority=OrderPriority.URGENT,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=2)],
    )
    result = _merge_work_orders([o1, o2])
    assert result.priority == OrderPriority.URGENT
    assert len(result.items) == 2
    assert result.items[0].item_id == 1
    assert result.items[1].item_id == 2
