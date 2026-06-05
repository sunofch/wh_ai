"""第 1 步：统一契约 + 共享状态的单元测试。"""
from __future__ import annotations

from src.agents.base import BaseAgent
from src.agents.schemas import ParsedInstruction
from src.agents.state import FINISH, AgentState
from src.warehouse.models import OrderPriority, WorkOrder


def test_agent_state_defaults_are_empty():
    # Arrange / Act
    state = AgentState()

    # Assert
    assert state.user_input == ""
    assert state.image is None
    assert state.instructions == []
    assert state.work_order is None
    assert state.next == ""
    assert state.history == []
    assert state.metadata == {}


def test_with_updates_returns_new_instance_without_mutating_original():
    # Arrange
    original = AgentState(user_input="领3个泵备件")

    # Act
    updated = original.with_updates(next="inventory_agent")

    # Assert — 原对象不被修改（不可变更新）
    assert original.next == ""
    assert updated.next == "inventory_agent"
    assert updated.user_input == "领3个泵备件"
    assert updated is not original


def test_mark_done_appends_agent_to_history_immutably():
    # Arrange
    state = AgentState().mark_done("instruction_agent")

    # Act
    state2 = state.mark_done("inventory_agent")

    # Assert
    assert state.history == ["instruction_agent"]
    assert state2.history == ["instruction_agent", "inventory_agent"]


def test_state_carries_typed_instructions_and_work_order():
    # Arrange
    instructions = [ParsedInstruction(part_name="泵", model="P-100", quantity=3)]
    order = WorkOrder(order_id=1, source="vlm", priority=OrderPriority.NORMAL)

    # Act
    state = AgentState(instructions=instructions, work_order=order)

    # Assert
    assert state.instructions[0].part_name == "泵"
    assert state.work_order.order_id == 1


def test_finish_marker_is_distinct_constant():
    assert FINISH == "FINISH"
    assert AgentState().next != FINISH


def test_minimal_agent_satisfies_baseagent_protocol():
    # Arrange — 一个最小实现，验证 Protocol 契约可被满足
    class _Echo:
        name = "echo"
        description = "测试用回显 Agent"

        def run(self, state: AgentState) -> AgentState:
            return state.mark_done(self.name)

    agent = _Echo()

    # Act
    result = agent.run(AgentState(user_input="hi"))

    # Assert
    assert isinstance(agent, BaseAgent)
    assert result.history == ["echo"]
