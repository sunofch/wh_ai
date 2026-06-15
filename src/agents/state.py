"""跨 Agent 共享状态。

替代原先 Supervisor 与各 Agent 之间用 json.dumps / json.loads 传字符串的做法：
所有 Agent 读写同一个带类型的 AgentState，字段拼写或类型错误在校验阶段即暴露，
中途也不会因 JSON 解析失败而丢信息。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.agents.schemas import InventoryReport, ParsedInstruction, WarningReport
from src.warehouse.models import WorkOrder

# 路由终止标记：Supervisor 写入 next 表示无需再调用任何 Agent。
FINISH = "FINISH"


class AgentState(BaseModel):
    """Supervisor 与各 Agent 共享的状态对象。

    每个 Agent 读取所需字段、写回自己的产出，统一通过 run(state) -> state 流转。
    """

    # ── 输入 ──────────────────────────────────────────────
    user_input: str = ""
    image: str | None = None

    # ── instruction_agent 产出 ────────────────────────────
    instructions: list[ParsedInstruction] = Field(default_factory=list)

    # ── inventory_agent 产出（出入库意图）──────────────────
    work_order: WorkOrder | None = None

    # ── inventory_agent 产出（查询意图）────────────────────
    inventory_report: InventoryReport | None = None
    intent: str = ""  # inventory_agent 写入：本次意图 query / order / warning

    # ── inventory_agent 产出（预警意图）────────────────────
    warning_report: WarningReport | None = None

    # ── 意图识别层产出 ────────────────────────────────────
    category: str = ""  # intent_node 写入：第1层意图 business / general
    reply: str = ""     # general_reply_node 写入：general 意图的回复文本

    # ── 路由控制 ──────────────────────────────────────────
    next: str = ""  # Supervisor 写入：下一个 Agent 名 / FINISH
    history: list[str] = Field(default_factory=list)  # 已执行 Agent，防死循环

    # ── 扩展位 ────────────────────────────────────────────
    metadata: dict[str, Any] = Field(default_factory=dict)

    def with_updates(self, **changes: Any) -> "AgentState":
        """返回应用变更后的新实例（不可变更新，绝不原地修改）。"""
        return self.model_copy(update=changes)

    def mark_done(self, agent_name: str) -> "AgentState":
        """记录某 Agent 已执行一次，供路由去重 / 防死循环使用。"""
        return self.model_copy(update={"history": [*self.history, agent_name]})
