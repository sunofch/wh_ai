from __future__ import annotations

from collections import deque

import numpy as np

from src.optimization.config import get_optimization_config
from src.optimization.models.dqn_agent import DoubleDQNAgent, Transition


class InventoryEnv:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.n_weeks = len(cfg["forecast"])

    def reset(self):
        self.stock = self.cfg["init_stock"]
        self.t = 0
        self.pipeline = deque([0.0] * self.cfg["lead_time"])
        self.history = []
        return self._get_state()

    def _get_state(self):
        f_now = self.cfg["forecast"][self.t]
        f_total = sum(self.cfg["forecast"][self.t:])
        in_transit = sum(self.pipeline)
        return np.array([self.stock, in_transit, f_now, f_total], dtype=np.float32)

    def step(self, action):
        self.pipeline.append(float(action))
        arrived = self.pipeline.popleft() if self.pipeline else 0.0
        self.stock += arrived
        demand = self.cfg["forecast"][self.t]
        shortage = max(demand - self.stock, 0.0)
        self.stock = max(self.stock - demand, 0.0)
        cost = (
            self.cfg["holding_cost"] * self.stock
            + self.cfg["stockout_cost"] * shortage
            + (15.0 if action > 0 else 0.0)
        )
        self.history.append({
            "week": self.t + 1,
            "order": action,
            "arrived": arrived,
            "demand": demand,
            "shortage": shortage,
            "stock_end": self.stock,
            "cost": cost,
        })
        self.t += 1
        done = self.t >= self.n_weeks
        return (self._get_state() if not done else None), -cost, done


class RLOptimizer:
    def __init__(self, env_cfg: dict, action_space: list[int]):
        self.env = InventoryEnv(env_cfg)
        self.action_space = action_space
        self.agent = DoubleDQNAgent(state_dim=4, action_dim=len(action_space))

    def train(self):
        cfg = get_optimization_config()
        for ep in range(cfg.dqn_episodes):
            state = self.env.reset()
            while True:
                idx = self.agent.select_action(state)
                next_state, reward, done = self.env.step(self.action_space[idx])
                self.agent.buffer.append(Transition(
                    state,
                    idx,
                    reward,
                    next_state if next_state is not None else np.zeros_like(state),
                    done,
                ))
                self.agent.learn()
                if done:
                    break
                state = next_state
            if ep % cfg.dqn_target_update_freq == 0:
                self.agent.target_net.load_state_dict(self.agent.online_net.state_dict())
        return self.env.history
