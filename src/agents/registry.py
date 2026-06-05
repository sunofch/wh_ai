"""可被 Supervisor 路由调度的 Agent 注册表。

新增一个进路由的 Agent 时，只需在此处登记一行——
Supervisor 的路由提示会自动带上它的 name 与 description，路由代码无需改动。

注意：agv_agent 不在此处登记，它由 scheduler_loop 定时旁路触发，
不参与 LLM 路由（其 run 签名与本类 Agent 不同）。
"""
from __future__ import annotations

from src.agents.base import BaseAgent
from src.agents.instruction.agent import InstructionAgent
from src.agents.inventory.agent import InventoryAgent

# 登记顺序即确定性兜底路由的默认执行顺序（先解析、后建单）。
_ROUTED_AGENTS: tuple[BaseAgent, ...] = (
    InstructionAgent(),
    InventoryAgent(),
)


def build_registry() -> dict[str, BaseAgent]:
    """返回 {name: agent} 注册表（保持登记顺序）。"""
    return {agent.name: agent for agent in _ROUTED_AGENTS}
