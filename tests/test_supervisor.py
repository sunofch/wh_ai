"""Supervisor / Agent 基础测试。

LLM 路由编排的测试见 tests/test_router.py；
WorkOrder 合并逻辑的测试已随 _merge_work_orders 迁至 tests/test_inventory_agent.py。

本文件保留与编排范式无关的基础断言：
1. instruction_agent 名称常量正确
2. get_instruction_agent() 构建自定义 LangGraph
3. agv_agent.run() 纯算法调度路径可调用
"""
from unittest.mock import patch, MagicMock


# ── 1. 名称常量 ────────────────────────────────────────────────────────────────

def test_agent_name_constant():
    from src.agents.instruction.agent import AGENT_NAME
    assert AGENT_NAME == "instruction_agent"


# ── 2. get_instruction_agent 构建两个 ChatOpenAI 实例 ──────────────────────────

def test_get_instruction_agent_passes_name():
    """instruction_agent 为自定义 LangGraph，使用两个 ChatOpenAI 实例（llm_base + llm_lora）。"""
    mock_llm = MagicMock()

    with patch("src.agents.instruction.agent.ChatOpenAI", return_value=mock_llm) as MockChat:

        from src.agents.instruction.agent import get_instruction_agent
        get_instruction_agent.cache_clear()
        agent = get_instruction_agent()

    assert hasattr(agent, "invoke")
    assert MockChat.call_count == 2


# ── 3. agv_agent.run() 纯算法路径 ────────────────────────────────────────────

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
