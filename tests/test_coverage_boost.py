"""薄弱模块覆盖率补充测试：数据加载、RL 环境、LSTM、锚定存储、工具函数。"""
import types

import numpy as np
import pandas as pd
import pytest
import torch

from src.optimization.data_loader import PortDataLoader
from src.optimization.engine.optimizer import InventoryEnv, RLOptimizer
from src.optimization.models.lstm_model import MultiVarLSTM
from src.traceability.adapters import LocalAnchorStore
from src.traceability.merkle import merkle_root


# ── InventoryEnv ──

class TestInventoryEnv:
    CFG = {
        "forecast": [5.0, 3.0, 4.0],
        "init_stock": 10.0,
        "lead_time": 1,
        "holding_cost": 1.0,
        "stockout_cost": 10.0,
    }

    def test_reset_state(self):
        env = InventoryEnv(self.CFG)
        state = env.reset()
        assert state.shape == (4,)
        assert state[0] == 10.0          # 初始库存

    def test_step_consumes_demand(self):
        env = InventoryEnv(self.CFG)
        env.reset()
        _, reward, done = env.step(0)
        assert not done
        assert env.stock == 5.0          # 10 - 5
        assert reward < 0                # 成本为负奖励

    def test_episode_terminates(self):
        env = InventoryEnv(self.CFG)
        env.reset()
        done = False
        steps = 0
        while not done:
            _, _, done = env.step(2)
            steps += 1
        assert steps == 3
        assert len(env.history) == 3

    def test_stockout_penalized(self):
        cfg = {**self.CFG, "init_stock": 0.0}
        env = InventoryEnv(cfg)
        env.reset()
        _, reward_shortage, _ = env.step(0)
        env2 = InventoryEnv(self.CFG)
        env2.reset()
        _, reward_ok, _ = env2.step(0)
        assert reward_shortage < reward_ok


class TestRLOptimizer:
    def test_short_training_run(self, monkeypatch):
        import src.optimization.engine.optimizer as opt_mod

        stub_cfg = types.SimpleNamespace(dqn_episodes=2, dqn_target_update_freq=1)
        monkeypatch.setattr(opt_mod, "get_optimization_config", lambda: stub_cfg)

        torch.manual_seed(0)
        optimizer = RLOptimizer(TestInventoryEnv.CFG, action_space=[0, 5])
        optimizer.train()  # 不抛异常即视为链路通畅
        assert len(optimizer.env.history) == 3  # 最后一个 episode 的履历


# ── PortDataLoader ──

class TestPortDataLoader:
    def _frames(self):
        usage = pd.DataFrame({
            "date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-12"]),
            "spare_part": ["滤芯", "滤芯", "轴承"],
            "quantity_used": [2, 3, 1],
        })
        runtime = pd.DataFrame({
            "date": pd.to_datetime(["2026-01-04", "2026-01-05", "2026-01-06"]),
            "equipment_id": ["E1", "E1", "E1"],
            "run_hours": [10.0, 12.0, 8.0],
            "temperature": [60.0, 65.0, 70.0],
            "vibration": [0.5, 0.6, 0.9],
        })
        maintenance = pd.DataFrame({
            "date": pd.to_datetime(["2026-01-07"]),
            "spare_part": ["滤芯"],
            "equipment_id": ["E1"],
        })
        return usage, runtime, maintenance

    def test_causal_features_within_fault_window(self):
        loader = PortDataLoader("滤芯", pre_fault_window=3, raw_data_dir=".")
        usage, runtime, maintenance = self._frames()
        target_usage, daily_health = loader.extract_causal_features(usage, runtime, maintenance)
        assert target_usage["quantity_used"].sum() == 5
        # 故障前3天窗口（01-04..01-06）内的工况被纳入
        assert len(daily_health) == 3
        assert "vibration" in daily_health.columns

    def test_no_fault_records_returns_empty_health(self):
        loader = PortDataLoader("不存在的备件", raw_data_dir=".")
        usage, runtime, maintenance = self._frames()
        _, daily_health = loader.extract_causal_features(usage, runtime, maintenance)
        assert daily_health.empty

    def test_weekly_dataset_has_seasonal_encoding(self):
        loader = PortDataLoader("滤芯", pre_fault_window=3, raw_data_dir=".")
        usage, runtime, maintenance = self._frames()
        target_usage, daily_health = loader.extract_causal_features(usage, runtime, maintenance)
        weekly = loader.prepare_weekly_dataset(target_usage, daily_health)
        assert {"sin_week", "cos_week", "quantity_used"} <= set(weekly.columns)
        assert weekly["quantity_used"].sum() == 5


# ── MultiVarLSTM ──

class TestMultiVarLSTM:
    def test_forward_shape(self):
        model = MultiVarLSTM(input_size=6, hidden_size=16, num_layers=1)
        out = model(torch.randn(3, 8, 6))
        assert out.shape in ((3,), (3, 1))


# ── 锚定存储 ──

class TestLocalAnchorStore:
    def test_anchor_and_fetch(self):
        store = LocalAnchorStore()
        root = merkle_root(["a" * 64, "b" * 64])
        tx = store.anchor(root, height=10)
        assert tx.startswith("local-tx-10-")
        assert store.fetch_anchor(10) == root
        assert store.fetch_anchor(99) is None


# ── 消息打印工具 ──

class TestWorkOrderAssembler:
    def test_print_agent_messages(self, capsys):
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        from src.agents.work_order_assembler import print_agent_messages

        messages = [
            HumanMessage(content="出库1个轴承"),
            AIMessage(content="", tool_calls=[
                {"name": "query_inventory", "args": {"model": "M1"}, "id": "1"},
            ]),
            ToolMessage(content='{"available": 3}', tool_call_id="1", name="query_inventory"),
            ToolMessage(content="非JSON结果", tool_call_id="2", name="other"),
            AIMessage(content="完成"),
        ]
        print_agent_messages(messages)
        out = capsys.readouterr().out
        assert "query_inventory" in out
        assert "available" in out
        assert "完成" in out


# ── 通用工具 ──

class TestCommonUtils:
    def test_get_device_explicit_cpu(self):
        from src.common.utils import get_device

        assert get_device("cpu") == "cpu"

    def test_get_device_auto(self):
        from src.common.utils import get_device

        assert get_device("auto") in ("cpu", "cuda")
