"""Supervisor 两层意图识别 + BaseAgent 测试。

覆盖：
1. BaseAgent 包装 InstructionAgent / InventoryAgent 的 run(state)
2. 第2层意图分类规则 _classify_intent（business 链内细分 query/order）
3. inventory agent 查询分支
4. end-to-end supervisor.run()：business 链返回 WorkOrder / InventoryReport，不触发 AGV
"""
from unittest.mock import MagicMock, patch

from src.agents.schemas import ParsedInstruction
from src.agents.state import AgentState
from src.warehouse.models import InventoryItem, OrderItem, OrderPriority, TaskType, WorkOrder


def _stock_item(part_name="深沟球轴承", model="6208-2RS-C3-SKF-Mech1", available=81):
    return InventoryItem(
        model=model, part_name=part_name, en_name="Deep Groove Ball Bearing",
        quantity=100, reserved=100 - available, available=available,
        location="Mech1_R1_B1", zone="Mech1", max_capacity=120,
    )


# ── 1. BaseAgent 包装 ─────────────────────────────────────────────────────────

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
        ParsedInstruction(part_name="深沟球轴承", quantity=3, action_required="出库"),
        ParsedInstruction(part_name="液压泵", quantity=1, action_required="出库"),
    ])

    with patch("src.agents.inventory.agent.get_inventory_agent", return_value=mock_pipeline):
        state = InventoryAgent().run(state0)

    assert state.intent == "order"
    assert mock_pipeline.run.call_count == 2
    assert state.work_order.priority == OrderPriority.URGENT
    assert len(state.work_order.items) == 2


# ── 2. end-to-end supervisor.run()（business 链）───────────────────────────────

def _patch_intent_business():
    """强制第1层意图为 business，走业务链 instruction → inventory。"""
    from src.agents.intent import IntentDecision

    structured = MagicMock()
    structured.invoke.return_value = IntentDecision(category="business")
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return patch("src.agents.intent._get_intent_llm", return_value=llm)


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

    with _patch_intent_business(), \
         patch("src.agents.instruction.agent.get_instruction_agent", return_value=mock_instr_graph), \
         patch("src.agents.inventory.agent.get_inventory_agent", return_value=mock_inv_pipeline):
        result = run(text="需要3个深沟球轴承出库")

    assert result.intent == "order"
    assert result.result.kind == "work_order"
    assert len(result.result.order.items) == 1
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

    with _patch_intent_business(), \
         patch("src.agents.instruction.agent.get_instruction_agent", return_value=mock_instr_graph), \
         patch("src.agents.inventory.agent.get_inventory_agent", return_value=mock_inv_pipeline), \
         patch("src.agents.agv.agent.run") as mock_agv:
        run(text="液压泵1台入库")

    mock_agv.assert_not_called()


# ── 3. 第2层意图分类（规则）───────────────────────────────────────────────────

def test_classify_intent_order_when_action_present():
    from src.agents.inventory.agent import _classify_intent
    insts = [ParsedInstruction(part_name="深沟球轴承", quantity=3, action_required="出库")]
    assert _classify_intent(insts) == "order"


def test_classify_intent_query_when_no_action():
    from src.agents.inventory.agent import _classify_intent
    insts = [ParsedInstruction(part_name="深沟球轴承")]  # 无出入库动作
    assert _classify_intent(insts) == "query"


def test_classify_intent_empty_defaults_to_order():
    from src.agents.inventory.agent import _classify_intent
    assert _classify_intent([]) == "order"


# ── 4. inventory agent 查询分支 ───────────────────────────────────────────────

def test_inventory_agent_run_query_branch_builds_report():
    from src.agents.inventory.agent import InventoryAgent
    from src.agents.schemas import InventoryReport

    state0 = AgentState(instructions=[ParsedInstruction(part_name="深沟球轴承")])

    with patch("src.agents.inventory.agent.lookup_stock_item", return_value=_stock_item()):
        state = InventoryAgent().run(state0)

    assert state.intent == "query"
    assert state.work_order is None
    assert isinstance(state.inventory_report, InventoryReport)
    assert len(state.inventory_report.items) == 1
    assert state.inventory_report.items[0].available == 81


# ── 5. end-to-end 查询返回 AgentResult(InventoryReport)────────────────────────

def test_run_query_returns_inventory_report():
    from src.agents.supervisor import run

    mock_instr_graph = MagicMock()
    mock_instr_graph.invoke.return_value = {
        "messages": [MagicMock(content='[{"part_name": "深沟球轴承"}]')]  # 无 action_required → 查询
    }

    with _patch_intent_business(), \
         patch("src.agents.instruction.agent.get_instruction_agent", return_value=mock_instr_graph), \
         patch("src.agents.inventory.agent.lookup_stock_item", return_value=_stock_item()):
        result = run(text="深沟球轴承还有多少")

    assert result.intent == "query"
    assert result.result.kind == "inventory_report"
    assert len(result.result.items) == 1
    assert result.result.items[0].part_name == "深沟球轴承"
