"""Supervisor / Router Agent 测试。

测试范围：
1. instruction_agent 名称常量正确
2. get_instruction_agent() 以正确 name 调用 create_react_agent
3. get_supervisor() 将 instruction_agent 传入 create_supervisor
4. run() 经 Supervisor 消息链正确提取指令并返回 WorkOrder
"""
import json
from unittest.mock import patch, MagicMock


# ── 1. 名称常量 ────────────────────────────────────────────────────────────────

def test_agent_name_constant():
    from src.agents.instruction_agent import AGENT_NAME
    assert AGENT_NAME == "instruction_agent"


# ── 2. get_instruction_agent 传入正确的 name ───────────────────────────────────

def test_get_instruction_agent_passes_name():
    """create_react_agent 必须收到 name='instruction_agent'。"""
    with patch("src.agents.instruction_agent.ChatOpenAI"), \
         patch("src.agents.instruction_agent.create_react_agent") as mock_create:
        mock_create.return_value = MagicMock()

        # 清除 lru_cache 以强制重新执行
        from src.agents.instruction_agent import get_instruction_agent
        get_instruction_agent.cache_clear()
        get_instruction_agent()

        _, kwargs = mock_create.call_args
        assert kwargs.get("name") == "instruction_agent"


# ── 3. get_supervisor 将 instruction_agent 挂载进去 ────────────────────────────

def test_get_supervisor_includes_instruction_agent():
    """create_supervisor 收到的 agents 列表包含 instruction_agent。"""
    mock_agent = MagicMock(name="instruction_agent")

    with patch("src.agents.supervisor.get_instruction_agent", return_value=mock_agent), \
         patch("src.agents.supervisor._get_supervisor_llm"), \
         patch("src.agents.supervisor.create_supervisor") as mock_cs:
        compiled = MagicMock()
        mock_cs.return_value.compile.return_value = compiled

        from src.agents.supervisor import get_supervisor
        get_supervisor.cache_clear()
        get_supervisor()

        agents_arg = mock_cs.call_args.kwargs.get("agents") or mock_cs.call_args.args[0]
        assert mock_agent in agents_arg


# ── 4. run() 从 Supervisor 消息链返回 WorkOrder ────────────────────────────────

def _make_supervisor_messages(instruction_fields: dict, inventory_json: str | None = None):
    """模拟 Supervisor 图返回的消息列表。

    结构：
      HumanMessage → Supervisor 路由 AIMessage → instruction_agent 工具调用
      → ToolMessage(query_inventory) → instruction_agent 最终 AIMessage(JSON)
      → Supervisor 总结 AIMessage（非 JSON）
    """
    from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

    msgs = [HumanMessage(content="测试输入")]
    if inventory_json:
        msgs.append(ToolMessage(
            content=inventory_json,
            tool_call_id="query_inventory",
            name="query_inventory",
        ))
    # instruction_agent 最终输出（含 JSON）
    msgs.append(AIMessage(content=json.dumps(instruction_fields, ensure_ascii=False)))
    # Supervisor 总结（纯文字，不含 JSON）
    msgs.append(AIMessage(content="已完成领料解析，工单已生成。"))
    return msgs


def test_run_returns_work_order_via_supervisor():
    """run() 透过 Supervisor 消息链正确组装 WorkOrder。"""
    from src.warehouse.models import WorkOrder, OrderItem, TaskType, OrderPriority

    mock_order = WorkOrder(
        order_id=1, source="supervisor", priority=OrderPriority.NORMAL,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=3)],
    )
    msgs = _make_supervisor_messages({
        "part_name": "深沟球轴承", "quantity": 3,
        "model": "6208-Mech1", "action_required": "出库", "is_urgent": False,
    })

    with patch("src.agents.supervisor.get_supervisor") as mock_gs, \
         patch("src.agent.agent.StockManager"), \
         patch("src.agent.agent.OrderManager") as MockOM:
        app = MagicMock()
        mock_gs.return_value = app
        app.invoke.return_value = {"messages": msgs}
        MockOM.return_value.from_port_instruction.return_value = mock_order

        from src.agents.supervisor import run
        result = run(text="需要3个深沟球轴承出库")

    assert isinstance(result, WorkOrder)
    assert result.items[0].quantity == 3


def test_run_skips_supervisor_summary_picks_instruction_json():
    """_assemble_work_order 向后扫描，跳过 Supervisor 总结，找到 instruction_agent 的 JSON。"""
    from src.warehouse.models import WorkOrder, OrderPriority

    mock_order = WorkOrder(order_id=2, source="supervisor", priority=OrderPriority.NORMAL)
    msgs = _make_supervisor_messages({
        "part_name": "液压泵", "quantity": 1,
        "model": "HPU-300", "action_required": "入库", "is_urgent": True,
    })

    with patch("src.agents.supervisor.get_supervisor") as mock_gs, \
         patch("src.agent.agent.StockManager"), \
         patch("src.agent.agent.OrderManager") as MockOM:
        app = MagicMock()
        mock_gs.return_value = app
        app.invoke.return_value = {"messages": msgs}
        MockOM.return_value.from_port_instruction.return_value = mock_order

        from src.agents.supervisor import run
        result = run(text="液压泵1台入库")

    assert isinstance(result, WorkOrder)
