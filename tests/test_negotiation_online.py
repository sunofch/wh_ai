"""博弈协商冲突消解 + DQN 在线学习测试。

对应 pj4 子课题 4.2：基于协同博弈的多 AGV 调度（竞价获得路权，
高紧急度/重载 AGV 先规划先锁定时空资源），以及在线学习机制
动态响应扰动（增量更新 + 目标网络软同步）。
"""
import numpy as np
import pytest
import torch

from src.warehouse.fleet.negotiation import Bid, compute_bid, plan_order
from src.warehouse.models import OrderPriority, TaskType, TransportTask


def _task(task_id: int, priority=OrderPriority.NORMAL) -> TransportTask:
    return TransportTask(
        task_id=task_id, task_type=TaskType.OUTBOUND, priority=priority,
        pick="Mech1_R1_B1", dest="PORT_OUT_1",
    )


# ── 竞价 ──

class TestBidding:
    def test_urgent_tasks_raise_bid(self):
        normal = compute_bid(agv_id=1, tasks=[_task(1)], battery=100)
        urgent = compute_bid(agv_id=2, tasks=[_task(2, OrderPriority.URGENT)], battery=100)
        assert urgent.value > normal.value

    def test_heavier_workload_raises_bid(self):
        light = compute_bid(agv_id=1, tasks=[_task(1)], battery=100)
        heavy = compute_bid(agv_id=2, tasks=[_task(i) for i in range(5)], battery=100)
        assert heavy.value > light.value

    def test_low_battery_lowers_bid(self):
        full = compute_bid(agv_id=1, tasks=[_task(1)], battery=100)
        low = compute_bid(agv_id=2, tasks=[_task(2)], battery=15)
        assert low.value < full.value

    def test_bid_components_recorded(self):
        bid = compute_bid(agv_id=1, tasks=[_task(1)], battery=80)
        assert isinstance(bid, Bid)
        assert {"urgency", "workload", "battery"} <= set(bid.components)


# ── 规划顺序（协商结果）──

class TestPlanOrder:
    def test_urgent_agv_plans_first(self):
        bids = [
            compute_bid(agv_id=1, tasks=[_task(1)], battery=100),
            compute_bid(agv_id=2, tasks=[_task(2, OrderPriority.URGENT)], battery=100),
        ]
        assert plan_order(bids)[0] == 2

    def test_deterministic_tiebreak_by_id(self):
        bids = [
            compute_bid(agv_id=3, tasks=[_task(1)], battery=100),
            compute_bid(agv_id=1, tasks=[_task(2)], battery=100),
        ]
        assert plan_order(bids) == [1, 3]

    def test_empty(self):
        assert plan_order([]) == []


# ── 仿真集成：协商决定规划顺序 ──

class TestSimulatorIntegration:
    def test_simulation_still_completes(self):
        """协商排序接入后端到端仿真仍正常完成（回归保护）。"""
        from main_simulation import run_single
        from src.warehouse.wms.config import WarehouseConfig

        config = WarehouseConfig(ORDER_NUM=10)
        result, _, _ = run_single(config, "medium_57x47", 10)
        assert result.makespan > 0

    def test_simulator_plans_urgent_agv_first(self):
        """带紧急任务的 AGV 应先于普通 AGV 规划（获得路权）。"""
        from src.warehouse.fleet.negotiation import compute_bid, plan_order

        bids = [
            compute_bid(agv_id=1, tasks=[_task(1)], battery=100),
            compute_bid(agv_id=2, tasks=[_task(2, OrderPriority.URGENT)], battery=100),
            compute_bid(agv_id=3, tasks=[], battery=100),
        ]
        order = plan_order(bids)
        assert order[0] == 2
        assert order[-1] == 3  # 空载 AGV 最后规划


# ── DQN 在线学习 ──

class TestOnlineDQN:
    def _agent(self):
        from src.optimization.models.dqn_agent import DoubleDQNAgent
        torch.manual_seed(0)
        return DoubleDQNAgent(state_dim=4, action_dim=2)

    def test_observe_fills_buffer(self):
        agent = self._agent()
        s = np.zeros(4, dtype=np.float32)
        agent.observe(s, 0, 1.0, s, False)
        assert len(agent.buffer) == 1

    def test_learn_online_updates_weights(self):
        agent = self._agent()
        rng = np.random.default_rng(0)
        before = [p.clone() for p in agent.online_net.parameters()]
        for _ in range(40):
            s = rng.normal(size=4).astype(np.float32)
            loss = agent.learn_online(s, 0, 1.0, s + 0.1, False, batch_size=8)
        assert loss is not None
        after = list(agent.online_net.parameters())
        assert any(not torch.equal(b, a) for b, a in zip(before, after))

    def test_target_net_soft_synced(self):
        agent = self._agent()
        rng = np.random.default_rng(1)
        for _ in range(60):
            s = rng.normal(size=4).astype(np.float32)
            agent.learn_online(s, 1, -1.0, s, False, batch_size=8)
        online = torch.cat([p.flatten() for p in agent.online_net.parameters()])
        target = torch.cat([p.flatten() for p in agent.target_net.parameters()])
        # 软同步后目标网络应向在线网络靠拢但不完全一致
        assert not torch.equal(online, target)
        assert torch.norm(online - target) < torch.norm(online) * 0.5
