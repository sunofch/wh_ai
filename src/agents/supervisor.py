"""Supervisor：两层意图识别编排。

第1层（intent_node, LLM）把请求粗分为 business / general：
  - business → instruction_agent → inventory_agent（inventory 内部第2层规则细分 query/order）
  - general  → general_reply_node 直接产出回复

图结构：
    START → intent ─┬─ business → instruction_agent → inventory_agent → END
                    └─ general  → general_reply ───────────────────────→ END

AGV 调度不在此处发生，由 scheduler_loop 触发 agv_agent 独立执行。
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from src.agents.base import BaseAgent
from src.agents.intent import (
    BUSINESS,
    FALLBACK_REPLY,
    GENERAL,
    classify_intent,
    general_reply,
)
from src.agents.registry import build_registry
from src.agents.schemas import AgentResult, GeneralReply, WorkOrderResult
from src.agents.state import AgentState
from src.warehouse.models import OrderPriority, WorkOrder


# ── 图节点 ────────────────────────────────────────────────────────────────────

def _intent_node(state: AgentState) -> dict:
    """第1层意图分类节点：写 state.category。"""
    return {"category": classify_intent(state)}


def _general_reply_node(state: AgentState) -> dict:
    """general 回复节点：写 state.reply。"""
    return {"reply": general_reply(state)}


def _make_agent_node(agent: BaseAgent):
    def agent_node(state: AgentState) -> dict:
        result = agent.run(state).mark_done(agent.name)
        updates = dict(result)
        updates.pop("next", None)
        return updates
    return agent_node


# ── 图构建 ────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_graph():
    registry = build_registry()  # {"instruction_agent": ..., "inventory_agent": ...}

    graph = StateGraph(AgentState)
    graph.add_node("intent", _intent_node)
    graph.add_node("general_reply", _general_reply_node)
    for name, agent in registry.items():
        graph.add_node(name, _make_agent_node(agent))

    graph.add_edge(START, "intent")
    graph.add_conditional_edges("intent", lambda s: s.category, {
        BUSINESS: "instruction_agent",
        GENERAL: "general_reply",
    })
    # business 业务链：instruction_agent → inventory_agent → END
    graph.add_edge("instruction_agent", "inventory_agent")
    graph.add_edge("inventory_agent", END)
    graph.add_edge("general_reply", END)

    return graph.compile()


# ── 主入口（签名保持兼容）────────────────────────────────────────────────────

def run(
    text: str | None = None,
    image: str | None = None,
    verbose: bool = False,
) -> AgentResult:
    """Supervisor 主入口。返回统一结果信封 AgentResult，不涉及 AGV 调度。

    - general 意图  → AgentResult(intent="general", result=GeneralReply)
    - 查询意图      → AgentResult(intent="query",   result=InventoryReport)
    - 出入库意图    → AgentResult(intent="order",   result=WorkOrderResult)
    """
    initial = AgentState(user_input=text or "", image=image)
    final = _get_graph().invoke(initial)

    if isinstance(final, AgentState):
        category, intent = final.category, final.intent
        report, work_order, reply = final.inventory_report, final.work_order, final.reply
    else:  # LangGraph 返回 channel 值映射
        category, intent = final.get("category", ""), final.get("intent", "")
        report = final.get("inventory_report")
        work_order = final.get("work_order")
        reply = final.get("reply", "")

    if verbose:
        print(f"[supervisor] category={category} intent={intent}")

    if category == GENERAL:
        return AgentResult(
            intent="general",
            result=GeneralReply(text=reply or FALLBACK_REPLY),
        )

    if intent == "query" and report is not None:
        return AgentResult(intent="query", result=report)

    order = work_order or WorkOrder(
        order_id=0, source="vlm", priority=OrderPriority.NORMAL
    )
    return AgentResult(intent=intent or "order", result=WorkOrderResult(order=order))
