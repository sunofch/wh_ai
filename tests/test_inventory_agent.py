"""Inventory Management Agent 测试。

测试范围：
1. create_work_order 工具创建工单
2. create_restock_order 工具创建补货单
3. inventory_agent 名称常量正确
4. get_inventory_agent() 以正确 name 调用 create_react_agent
5. Supervisor 经 inventory_agent 处理库存不足时返回带补货单号的 WorkOrder
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
    with patch("src.agent.tools.order_tool.OrderManager") as MockOM, \
         patch("src.agent.tools.order_tool.MapRegistry") as MockReg, \
         patch("src.warehouse.wms.inventory_db.StockManager"):
        MockReg.get.return_value = MagicMock()
        MockOM.return_value.from_port_instruction.return_value = mock_order

        from src.agent.tools.order_tool import create_work_order
        result = create_work_order.invoke({
            "part_name": "深沟球轴承", "model": "6208-Mech1",
            "quantity": 3, "action_required": "出库",
        })

    data = json.loads(result)
    assert data["status"] == "created"
    assert "items" in data
    assert data["items"][0]["quantity"] == 3


def test_create_work_order_returns_failed_when_none():
    with patch("src.agent.tools.order_tool.OrderManager") as MockOM, \
         patch("src.agent.tools.order_tool.MapRegistry") as MockReg, \
         patch("src.warehouse.wms.inventory_db.StockManager"):
        MockReg.get.return_value = MagicMock()
        MockOM.return_value.from_port_instruction.return_value = None

        from src.agent.tools.order_tool import create_work_order
        result = create_work_order.invoke({
            "part_name": "", "model": "", "quantity": 0, "action_required": "",
        })

    data = json.loads(result)
    assert data["status"] == "failed"


# ── 2. create_restock_order 工具 ──────────────────────────────────────────────

def test_create_restock_order_returns_order_id():
    with patch("src.agent.tools.order_tool.MapRegistry") as MockReg, \
         patch("src.agent.tools.order_tool.OrderManager") as MockOM:
        MockReg.get.return_value = MagicMock()
        MockOM.return_value.from_port_instruction.return_value = MagicMock()

        from src.agent.tools.order_tool import create_restock_order
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
    from src.agents.inventory_agent import AGENT_NAME
    assert AGENT_NAME == "inventory_agent"


# ── 4. get_inventory_agent 传入正确 name ──────────────────────────────────────

def test_get_inventory_agent_passes_name():
    with patch("src.agents.inventory_agent.ChatOpenAI"), \
         patch("src.agents.inventory_agent.create_react_agent") as mock_create:
        mock_create.return_value = MagicMock()

        from src.agents.inventory_agent import get_inventory_agent
        get_inventory_agent.cache_clear()
        get_inventory_agent()

        _, kwargs = mock_create.call_args
        assert kwargs.get("name") == "inventory_agent"


# ── 5. Supervisor 经 inventory_agent 返回带补货单号的 WorkOrder ────────────────

def test_supervisor_run_with_restock_via_inventory_agent():
    """库存不足时，inventory_agent 调用 create_restock_order，
    _assemble_work_order 从 ToolMessage 中提取补货单号写入 metadata。
    """
    from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
    from src.warehouse.models import WorkOrder, OrderPriority

    restock_result = json.dumps({"order_id": "RS-TEST1234", "status": "created",
                                  "message": "已生成补货入库订单，缺口数量: 3"})
    msgs = [
        HumanMessage(content="需要5个深沟球轴承出库"),
        # instruction_agent 解析结果
        AIMessage(content=json.dumps({
            "part_name": "深沟球轴承", "quantity": 5,
            "model": "6208-Mech1", "action_required": "出库", "is_urgent": False,
        })),
        # inventory_agent 调用 create_restock_order 的结果
        ToolMessage(content=restock_result, tool_call_id="create_restock_order",
                    name="create_restock_order"),
        # supervisor 总结
        AIMessage(content="库存不足，已创建补货单 RS-TEST1234。"),
    ]
    mock_order = WorkOrder(order_id=1, source="supervisor", priority=OrderPriority.NORMAL)

    with patch("src.agents.supervisor.get_supervisor") as mock_gs, \
         patch("src.agent.agent.StockManager"), \
         patch("src.agent.agent.OrderManager") as MockOM:
        app = MagicMock()
        mock_gs.return_value = app
        app.invoke.return_value = {"messages": msgs}
        MockOM.return_value.from_port_instruction.return_value = mock_order

        from src.agents.supervisor import run
        result = run(text="需要5个深沟球轴承出库")

    assert isinstance(result, WorkOrder)
    assert result.metadata.get("restock_order_id") == "RS-TEST1234"
