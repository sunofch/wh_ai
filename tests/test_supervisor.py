"""Supervisor / Agent 测试。

测试范围：
1. instruction_agent 名称常量正确
2. get_instruction_agent() 构建自定义 LangGraph
3. supervisor.run() 经两步流水线返回 WorkOrder
4. agv_agent.run() 纯算法调度路径可调用
"""
from unittest.mock import patch, MagicMock


# ── 1. 名称常量 ────────────────────────────────────────────────────────────────

def test_agent_name_constant():
    from src.agents.instruction.agent import AGENT_NAME
    assert AGENT_NAME == "instruction_agent"


# ── 2. get_instruction_agent 传入正确的 name ───────────────────────────────────

def test_get_instruction_agent_passes_name():
    """instruction_agent 已改为自定义 LangGraph，使用两个 ChatOpenAI 实例（llm_base + llm_lora）。"""
    mock_llm = MagicMock()

    with patch("src.agents.instruction.agent.ChatOpenAI", return_value=mock_llm) as MockChat:

        from src.agents.instruction.agent import get_instruction_agent
        get_instruction_agent.cache_clear()
        agent = get_instruction_agent()

    assert hasattr(agent, "invoke")
    assert MockChat.call_count == 2


def test_run_returns_work_order():
    """supervisor.run() 经两步流水线正确返回 WorkOrder。"""
    import json
    from src.warehouse.models import WorkOrder, OrderItem, TaskType, OrderPriority

    mock_order = WorkOrder(
        order_id=1, source="vlm", priority=OrderPriority.NORMAL,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=3)],
    )
    parsed_json = '[{"part_name": "深沟球轴承", "quantity": 3, "action_required": "出库"}]'
    msgs1 = [MagicMock(content=parsed_json)]

    mock_instruction_agent = MagicMock()
    mock_instruction_agent.invoke.return_value = {"messages": msgs1}

    mock_inventory_agent = MagicMock()
    mock_inventory_agent.run.return_value = mock_order

    with patch("src.agents.supervisor.get_instruction_agent", return_value=mock_instruction_agent), \
         patch("src.agents.supervisor.get_inventory_agent", return_value=mock_inventory_agent):

        from src.agents.supervisor import run
        result = run(text="需要3个深沟球轴承出库")

    assert isinstance(result, WorkOrder)
    expected_arg = json.dumps(
        {"part_name": "深沟球轴承", "quantity": 3, "action_required": "出库"},
        ensure_ascii=False,
    )
    mock_inventory_agent.run.assert_called_once_with(expected_arg)


def test_run_multiple_instructions():
    """supervisor.run() 多条备件时分别调用 inventory_agent 并合并为单个 WorkOrder。"""
    import json
    from src.warehouse.models import WorkOrder, OrderItem, TaskType, OrderPriority

    order_a = WorkOrder(
        order_id=1, source="vlm", priority=OrderPriority.NORMAL,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=3)],
    )
    order_b = WorkOrder(
        order_id=2, source="vlm", priority=OrderPriority.URGENT,
        items=[OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=1)],
    )
    parsed_json = '[{"part_name": "深沟球轴承", "quantity": 3}, {"part_name": "液压泵", "quantity": 1}]'
    msgs1 = [MagicMock(content=parsed_json)]

    mock_instruction_agent = MagicMock()
    mock_instruction_agent.invoke.return_value = {"messages": msgs1}

    mock_inventory_agent = MagicMock()
    mock_inventory_agent.run.side_effect = [order_a, order_b]

    with patch("src.agents.supervisor.get_instruction_agent", return_value=mock_instruction_agent), \
         patch("src.agents.supervisor.get_inventory_agent", return_value=mock_inventory_agent):

        from src.agents.supervisor import run
        result = run(text="需要3个深沟球轴承出库，紧急补一台液压泵")

    assert isinstance(result, WorkOrder)
    assert result.priority == OrderPriority.URGENT
    assert len(result.items) == 2
    assert mock_inventory_agent.run.call_count == 2


def test_merge_work_orders_empty():
    """_merge_work_orders 空列表返回默认 WorkOrder。"""
    from src.agents.supervisor import _merge_work_orders
    from src.warehouse.models import WorkOrder, OrderPriority
    result = _merge_work_orders([])
    assert isinstance(result, WorkOrder)
    assert result.priority == OrderPriority.NORMAL
    assert result.items == []


def test_merge_work_orders_single():
    """_merge_work_orders 单个 WorkOrder 原样返回。"""
    from src.agents.supervisor import _merge_work_orders
    from src.warehouse.models import WorkOrder, OrderPriority
    order = WorkOrder(order_id=1, source="vlm", priority=OrderPriority.NORMAL)
    result = _merge_work_orders([order])
    assert result is order


def test_merge_work_orders_multiple():
    """_merge_work_orders 多个 WorkOrder 取最高优先级，合并 items 并重新编号。"""
    from src.agents.supervisor import _merge_work_orders
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


def test_run_no_agv_scheduling():
    """supervisor.run() 不触发 AGV 调度，agv_agent 不被调用。"""
    msgs1 = [MagicMock(content="液压泵 1台 入库")]

    mock_instruction_agent = MagicMock()
    mock_instruction_agent.invoke.return_value = {"messages": msgs1}

    mock_inventory_agent = MagicMock()
    mock_inventory_agent.run.return_value = MagicMock()

    with patch("src.agents.supervisor.get_instruction_agent", return_value=mock_instruction_agent), \
         patch("src.agents.supervisor.get_inventory_agent", return_value=mock_inventory_agent), \
         patch("src.agents.agv.agent.run") as mock_agv:

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

    with patch("src.agents.agv.agent.TaskDecomposer") as MockTD, \
         patch("src.agents.agv.agent.OrderClusterer") as MockCluster, \
         patch("src.agents.agv.agent.Simulator") as MockSim:
        MockTD.return_value.decompose.return_value = []
        MockCluster.return_value.cluster.return_value = []
        MockSim.return_value.run.return_value = mock_sim_result

        from src.agents.agv.agent import run as agv_run
        sched, sim = agv_run(
            orders, mock_wmap, mock_fleet, mock_config,
            [], [], "test-run-id"
        )

    assert sched.run_id == "test-run-id"
    assert sched.order_count == 1
    MockTD.return_value.decompose.assert_called_once()
    MockCluster.return_value.cluster.assert_called_once()
    MockSim.return_value.run.assert_called_once()
