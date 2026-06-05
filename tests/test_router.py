"""LLM 路由 Supervisor 测试。

覆盖：
1. 确定性兜底路由 _fallback_next（无 LLM）
2. LLM 决策 _decide_next（mock LLM / 非法输出 / 异常退化）
3. max_steps 兜底防死循环
4. BaseAgent 包装 InstructionAgent / InventoryAgent 的 run(state)
5. end-to-end supervisor.run() 返回合并后的单个 WorkOrder，且不触发 AGV
"""
from unittest.mock import MagicMock, patch

from src.agents.schemas import ParsedInstruction
from src.agents.state import FINISH, AgentState
from src.warehouse.models import OrderItem, OrderPriority, TaskType, WorkOrder


def _registry():
    """构造与生产一致的双 Agent registry（顺序：instruction → inventory）。"""
    from src.agents.registry import build_registry
    return build_registry()


# ── 1. 确定性兜底路由 ─────────────────────────────────────────────────────────

def test_fallback_picks_first_unexecuted_agent():
    from src.agents.supervisor import _fallback_next
    reg = _registry()

    # 未执行任何 Agent → 选登记顺序第一个（instruction）
    assert _fallback_next(AgentState(), reg) == "instruction_agent"


def test_fallback_advances_to_next_after_first_done():
    from src.agents.supervisor import _fallback_next
    reg = _registry()

    state = AgentState(history=["instruction_agent"])
    assert _fallback_next(state, reg) == "inventory_agent"


def test_fallback_finishes_when_all_executed():
    from src.agents.supervisor import _fallback_next
    reg = _registry()

    state = AgentState(history=["instruction_agent", "inventory_agent"])
    assert _fallback_next(state, reg) == FINISH


# ── 2. LLM 决策 ───────────────────────────────────────────────────────────────

def test_decide_next_uses_llm_decision_when_valid():
    from src.agents.supervisor import RouteDecision, _decide_next
    reg = _registry()

    mock_structured = MagicMock()
    mock_structured.invoke.return_value = RouteDecision(next="inventory_agent", reason="已有指令")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured

    with patch("src.agents.supervisor._get_router_llm", return_value=mock_llm):
        result = _decide_next(AgentState(instructions=[ParsedInstruction(part_name="泵")]), reg)

    assert result == "inventory_agent"


def test_decide_next_falls_back_on_invalid_llm_output():
    from src.agents.supervisor import RouteDecision, _decide_next
    reg = _registry()

    mock_structured = MagicMock()
    mock_structured.invoke.return_value = RouteDecision(next="不存在的agent")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured

    with patch("src.agents.supervisor._get_router_llm", return_value=mock_llm):
        # 非法 next → 退化为兜底（空 history → instruction）
        result = _decide_next(AgentState(), reg)

    assert result == "instruction_agent"


def test_decide_next_falls_back_on_llm_exception():
    from src.agents.supervisor import _decide_next
    reg = _registry()

    with patch("src.agents.supervisor._get_router_llm", side_effect=RuntimeError("no server")):
        result = _decide_next(AgentState(), reg)

    assert result == "instruction_agent"


# ── 3. max_steps 兜底 ─────────────────────────────────────────────────────────

def test_router_node_finishes_when_max_steps_reached():
    from src.agents.supervisor import _make_router_node
    reg = _registry()

    node = _make_router_node(reg, max_steps=2)
    state = AgentState(history=["instruction_agent", "inventory_agent"])

    # 已达步数上限，直接 FINISH，不再询问 LLM
    assert node(state) == {"next": FINISH}


# ── 4. BaseAgent 包装 ─────────────────────────────────────────────────────────

def test_instruction_agent_run_writes_typed_instructions():
    from src.agents.instruction.agent import InstructionAgent

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "messages": [MagicMock(content='[{"part_name": "深沟球轴承", "quantity": 2}]')]
    }

    with patch("src.agents.instruction.agent.get_instruction_agent", return_value=mock_graph):
        state = InstructionAgent().run(AgentState(user_input="要2个深沟球轴承"))

    assert len(state.instructions) == 1
    assert isinstance(state.instructions[0], ParsedInstruction)
    assert state.instructions[0].part_name == "深沟球轴承"
    assert state.instructions[0].quantity == 2


def test_inventory_agent_run_fans_out_and_merges():
    from src.agents.inventory.agent import InventoryAgent

    order_a = WorkOrder(
        order_id=1, source="vlm", priority=OrderPriority.NORMAL,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=3)],
    )
    order_b = WorkOrder(
        order_id=2, source="vlm", priority=OrderPriority.URGENT,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=1)],
    )
    mock_pipeline = MagicMock()
    mock_pipeline.run.side_effect = [order_a, order_b]

    state0 = AgentState(instructions=[
        ParsedInstruction(part_name="深沟球轴承", quantity=3),
        ParsedInstruction(part_name="液压泵", quantity=1),
    ])

    with patch("src.agents.inventory.agent.get_inventory_agent", return_value=mock_pipeline):
        state = InventoryAgent().run(state0)

    assert mock_pipeline.run.call_count == 2
    assert state.work_order.priority == OrderPriority.URGENT
    assert len(state.work_order.items) == 2


# ── 5. end-to-end supervisor.run() ────────────────────────────────────────────

def _patch_router_to_fallback():
    """让路由 LLM 不可用，强制走确定性兜底（instruction → inventory → FINISH）。"""
    return patch("src.agents.supervisor._get_router_llm", side_effect=RuntimeError("no server"))


def test_run_returns_merged_work_order():
    from src.agents.supervisor import run

    mock_instr_graph = MagicMock()
    mock_instr_graph.invoke.return_value = {
        "messages": [MagicMock(content='[{"part_name": "深沟球轴承", "quantity": 3, "action_required": "出库"}]')]
    }
    expected_order = WorkOrder(
        order_id=1, source="vlm", priority=OrderPriority.NORMAL,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=3)],
    )
    mock_inv_pipeline = MagicMock()
    mock_inv_pipeline.run.return_value = expected_order

    with _patch_router_to_fallback(), \
         patch("src.agents.instruction.agent.get_instruction_agent", return_value=mock_instr_graph), \
         patch("src.agents.inventory.agent.get_inventory_agent", return_value=mock_inv_pipeline):
        result = run(text="需要3个深沟球轴承出库")

    assert isinstance(result, WorkOrder)
    assert len(result.items) == 1
    mock_inv_pipeline.run.assert_called_once()


def test_run_does_not_trigger_agv():
    from src.agents.supervisor import run

    mock_instr_graph = MagicMock()
    mock_instr_graph.invoke.return_value = {
        "messages": [MagicMock(content='[{"part_name": "液压泵", "quantity": 1, "action_required": "入库"}]')]
    }
    mock_inv_pipeline = MagicMock()
    mock_inv_pipeline.run.return_value = WorkOrder(
        order_id=1, source="vlm", priority=OrderPriority.NORMAL
    )

    with _patch_router_to_fallback(), \
         patch("src.agents.instruction.agent.get_instruction_agent", return_value=mock_instr_graph), \
         patch("src.agents.inventory.agent.get_inventory_agent", return_value=mock_inv_pipeline), \
         patch("src.agents.agv.agent.run") as mock_agv:
        run(text="液压泵1台入库")

    mock_agv.assert_not_called()
