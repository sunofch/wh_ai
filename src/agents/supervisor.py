"""Supervisor：基于 LangGraph 的 LLM 路由编排。

由路由 LLM 根据用户请求与已完成步骤，动态决定下一个调用哪个 Agent
（或 FINISH 结束），而非写死的调用顺序。新增 Agent 只需在 registry 登记，
路由逻辑无需改动。

图结构：
    START → supervisor(路由节点) ─┬─ FINISH ─────────────▶ END
                                  └─ {agent_name} ─▶ agent ─┐
                                       ▲                     │
                                       └─────────────────────┘ (每个 Agent 跑完回 supervisor)

兜底：路由 LLM 不可用或输出非法时，退化为确定性顺序（按 registry 登记顺序
依次执行未完成的 Agent），保证流程永不卡死；max_steps + history 防死循环。

AGV 调度不在此处发生，由 scheduler_loop 触发 agv_agent 独立执行。
"""
from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from src.agents.base import BaseAgent
from src.agents.registry import build_registry
from src.agents.state import FINISH, AgentState
from src.common.config import config
from src.warehouse.models import OrderPriority, WorkOrder


class RouteDecision(BaseModel):
    """路由 LLM 的结构化输出。"""
    next: str
    reason: str = ""


# ── 路由 LLM ──────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_router_llm() -> ChatOpenAI:
    """构建路由 LLM。端口留空(0)时复用 instruction_agent 的 vLLM 端点。"""
    cfg = config.supervisor
    port = cfg.port or (config.vllm_server.base_port + 1)
    host = cfg.host or config.vllm_server.host
    return ChatOpenAI(
        base_url=f"http://{host}:{port}/v1",
        api_key="EMPTY",
        model=cfg.model,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )


def _build_router_messages(state: AgentState, registry: dict[str, BaseAgent]) -> list:
    """从 registry 动态拼出路由提示。"""
    options = [f"- FINISH：任务已完成，无需再调用任何 Agent，结束流程"]
    options += [f"- {name}：{agent.description}" for name, agent in registry.items()]
    done = "、".join(state.history) if state.history else "（无）"
    system = SystemMessage(content=(
        "你是仓储多 Agent 系统的路由器。根据用户请求与已完成的步骤，"
        "决定下一个应调用的 Agent；若任务已完成则返回 FINISH。"
        "next 只能从下列名称中选择：\n" + "\n".join(options)
    ))
    human = HumanMessage(content=(
        f"用户请求：{state.user_input or '（图片输入）'}\n"
        f"已完成步骤：{done}\n"
        f"是否已解析出 instructions：{'是' if state.instructions else '否'}\n"
        f"是否已生成 work_order：{'是' if state.work_order else '否'}\n"
        "请给出下一步 next 与简短 reason。"
    ))
    return [system, human]


def _fallback_next(state: AgentState, registry: dict[str, BaseAgent]) -> str:
    """确定性兜底：按登记顺序选第一个尚未执行的 Agent，全部执行过则 FINISH。"""
    for name in registry:
        if name not in state.history:
            return name
    return FINISH


def _decide_next(state: AgentState, registry: dict[str, BaseAgent]) -> str:
    """优先用 LLM 决策，失败或非法则退化到确定性兜底。"""
    valid = {FINISH, *registry.keys()}
    try:
        llm = _get_router_llm().with_structured_output(RouteDecision)
        decision = llm.invoke(_build_router_messages(state, registry))
        if decision is not None and decision.next in valid:
            return decision.next
    except Exception:
        pass
    return _fallback_next(state, registry)


# ── 图构建 ────────────────────────────────────────────────────────────────────

def _make_router_node(registry: dict[str, BaseAgent], max_steps: int):
    def router_node(state: AgentState) -> dict:
        if len(state.history) >= max_steps:
            return {"next": FINISH}
        return {"next": _decide_next(state, registry)}
    return router_node


def _make_agent_node(agent: BaseAgent):
    def agent_node(state: AgentState) -> dict:
        result = agent.run(state).mark_done(agent.name)
        updates = dict(result)
        updates.pop("next", None)  # next 由路由节点掌控
        return updates
    return agent_node


@lru_cache(maxsize=1)
def _get_graph():
    registry = build_registry()
    max_steps = config.supervisor.max_steps

    graph = StateGraph(AgentState)
    graph.add_node("supervisor", _make_router_node(registry, max_steps))
    for name, agent in registry.items():
        graph.add_node(name, _make_agent_node(agent))
        graph.add_edge(name, "supervisor")

    graph.add_edge(START, "supervisor")
    route_map = {name: name for name in registry}
    route_map[FINISH] = END
    graph.add_conditional_edges("supervisor", lambda s: s.next, route_map)

    return graph.compile()


# ── 主入口（签名保持兼容）────────────────────────────────────────────────────

def run(
    text: str | None = None,
    image: str | None = None,
    verbose: bool = False,
) -> WorkOrder:
    """Supervisor 主入口。返回合并后的单个 WorkOrder，不涉及 AGV 调度。"""
    initial = AgentState(user_input=text or "", image=image)
    final = _get_graph().invoke(initial)

    if isinstance(final, AgentState):
        work_order, history = final.work_order, final.history
    else:  # LangGraph 返回 channel 值映射
        work_order, history = final.get("work_order"), final.get("history", [])

    if verbose:
        print(f"[supervisor] 路由路径: {' → '.join(history) or '(空)'}")

    return work_order or WorkOrder(
        order_id=0, source="vlm", priority=OrderPriority.NORMAL
    )
