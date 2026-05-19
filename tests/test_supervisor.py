"""Supervisor / Agent 测试。

测试范围：
1. instruction_agent 名称常量正确
2. get_instruction_agent() 以正确 name 调用 create_react_agent
3. supervisor.run() 经两步流水线返回 WorkOrder
4. agv_agent.run() 纯算法调度路径可调用
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

        from src.agents.instruction_agent import get_instruction_agent
        get_instruction_agent.cache_clear()
        get_instruction_agent()

        _, kwargs = mock_create.call_args
        assert kwargs.get("name") == "instruction_agent"


# ── 3. supervisor.run() 两步流水线返回 WorkOrder ──────────────────────────────

def _make_inventory_messages(instruction_fields: dict):
    """模拟 inventory_agent 返回的消息列表，含 create_work_order ToolMessage。"""
    from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

    work_order_result = {
        "status": "created",
        "order_id": 1,
        "priority": "NORMAL",
        "items": [{
            "task_type": "OUTBOUND",
            "model": instruction_fields.get("model", ""),
            "part_name": instruction_fields.get("part_name", ""),
            "quantity": instruction_fields.get("quantity", 1),
            "pick": "S-01",
            "dest": "OUT-01",
        }],
    }
    return [
        HumanMessage(content="测试输入"),
        ToolMessage(
            content=json.dumps(work_order_result, ensure_ascii=False),
            tool_call_id="create_work_order",
            name="create_work_order",
        ),
        AIMessage(content=json.dumps(instruction_fields, ensure_ascii=False)),
    ]


def test_run_returns_work_order():
    """supervisor.run() 经两步流水线正确返回 WorkOrder。"""
    from src.warehouse.models import WorkOrder, OrderItem, TaskType, OrderPriority

    mock_order = WorkOrder(
        order_id=1, source="vlm", priority=OrderPriority.NORMAL,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=3)],
    )
    msgs1 = [MagicMock(content="深沟球轴承 3个 出库")]
    msgs2 = _make_inventory_messages({
        "part_name": "深沟球轴承", "quantity": 3,
        "model": "6208-Mech1", "action_required": "出库", "is_urgent": False,
    })

    mock_instruction_agent = MagicMock()
    mock_instruction_agent.invoke.return_value = {"messages": msgs1}

    mock_inventory_agent = MagicMock()
    mock_inventory_agent.invoke.return_value = {"messages": msgs2}

    with patch("src.agents.supervisor.get_instruction_agent", return_value=mock_instruction_agent), \
         patch("src.agents.supervisor.get_inventory_agent", return_value=mock_inventory_agent), \
         patch("src.agent.agent.StockManager"), \
         patch("src.agent.agent.OrderManager") as MockOM:
        MockOM.return_value.from_port_instruction.return_value = mock_order

        from src.agents.supervisor import run
        result = run(text="需要3个深沟球轴承出库")

    assert isinstance(result, WorkOrder)


def test_run_no_agv_scheduling():
    """supervisor.run() 不触发 AGV 调度，agv_agent 不被调用。"""
    msgs1 = [MagicMock(content="液压泵 1台 入库")]
    msgs2 = _make_inventory_messages({
        "part_name": "液压泵", "quantity": 1,
        "model": "HPU-300", "action_required": "入库", "is_urgent": False,
    })

    mock_instruction_agent = MagicMock()
    mock_instruction_agent.invoke.return_value = {"messages": msgs1}

    mock_inventory_agent = MagicMock()
    mock_inventory_agent.invoke.return_value = {"messages": msgs2}

    with patch("src.agents.supervisor.get_instruction_agent", return_value=mock_instruction_agent), \
         patch("src.agents.supervisor.get_inventory_agent", return_value=mock_inventory_agent), \
         patch("src.agent.agent.StockManager"), \
         patch("src.agent.agent.OrderManager") as MockOM, \
         patch("src.agents.agv_agent.run") as mock_agv:
        MockOM.return_value.from_port_instruction.return_value = MagicMock()

        from src.agents.supervisor import run
        run(text="液压泵1台入库")

    mock_agv.assert_not_called()


# ── 4. agv_agent.run() 纯算法路径 ────────────────────────────────────────────

def test_agv_agent_run_calls_pipeline():
    """agv_agent.run() 依次调用 TaskDecomposer、OrderClusterer、FleetManager、Simulator。"""
    from src.warehouse.models import WorkOrder, OrderPriority

    orders = [WorkOrder(order_id=1, source="vlm", priority=OrderPriority.NORMAL)]

    mock_wmap = MagicMock()
    mock_wmap.storage_list = []
    mock_wmap.zone_pos = {}

    mock_fleet = MagicMock()
    mock_fleet.path_finder = MagicMock()
    mock_fleet.schedule.return_value = {}

    mock_config = MagicMock()
    mock_config.RANDOM_SEED = 42
    mock_config.AGV_MAX_TASK_CAPACITY = 5

    mock_sim_result = MagicMock()
    mock_sim_result.makespan = 100
    mock_sim_result.total_distance = 500
    mock_sim_result.agv_utilization = 0.8
    mock_sim_result.planning_time = 0.1

    with patch("src.agents.agv_agent.TaskDecomposer") as MockTD, \
         patch("src.agents.agv_agent.OrderClusterer") as MockCluster, \
         patch("src.agents.agv_agent.Simulator") as MockSim:
        MockTD.return_value.decompose.return_value = []
        MockCluster.return_value.cluster.return_value = []
        MockSim.return_value.run.return_value = mock_sim_result

        from src.agents.agv_agent import run as agv_run
        sched, sim = agv_run(
            orders, mock_wmap, mock_fleet, mock_config,
            [], [], "test-run-id"
        )

    assert sched.run_id == "test-run-id"
    assert sched.order_count == 1
    MockTD.return_value.decompose.assert_called_once()
    MockCluster.return_value.cluster.assert_called_once()
    MockSim.return_value.run.assert_called_once()
