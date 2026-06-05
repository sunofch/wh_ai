"""统一 Agent 契约。

所有进入 Supervisor 路由的 Agent 都实现 BaseAgent 协议：
对外只暴露 name / description / run(state) 三样，
内部用什么范式（自定义 StateGraph / create_react_agent / 纯 Python 图）由各自封装。

这样 Supervisor 只需面对一种统一的调用方式 `agent.run(state)`，
并能从 description 动态构造路由提示，新增 Agent 无需改动路由代码。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.agents.state import AgentState


@runtime_checkable
class BaseAgent(Protocol):
    """可被 Supervisor 统一调度的 Agent 协议。

    属性:
        name:        唯一标识，路由决策与 history 去重均以此为准。
        description: 能力描述，供路由 LLM 判断是否应调用本 Agent。
    """

    name: str
    description: str

    def run(self, state: AgentState) -> AgentState:
        """读取 state 所需字段、写回自身产出，返回更新后的新 state。"""
        ...
