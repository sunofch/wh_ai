"""意图识别层（第1层）。

由 LLM 把用户输入粗分为 business / general 两类：
  - business：库存查询、出入库等仓储业务 → 进 instruction_agent → inventory_agent 业务链
  - general ：闲聊 / 无关 / 无法识别 → general_reply_node 直接回复

第2层（query/order 细分）仍由 inventory_agent 内部的 _classify_intent 规则完成。
"""
from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.agents.state import AgentState
from src.common.config import config

BUSINESS = "business"
GENERAL = "general"

# general_reply 的固定兜底文案（LLM 不可用时使用）
FALLBACK_REPLY = "我可以帮你查询备件库存或处理出入库，请描述你的需求。"


class IntentDecision(BaseModel):
    """第1层意图分类 LLM 的结构化输出。"""
    category: str
    reason: str = ""


def _endpoint() -> tuple[str, int]:
    """复用 supervisor 配置的 vLLM 端点；port 留空(0)时取 base_port+1。"""
    cfg = config.supervisor
    port = cfg.port or (config.vllm_server.base_port + 1)
    host = cfg.host or config.vllm_server.host
    return host, port


@lru_cache(maxsize=1)
def _get_intent_llm() -> ChatOpenAI:
    cfg = config.supervisor
    host, port = _endpoint()
    return ChatOpenAI(
        base_url=f"http://{host}:{port}/v1",
        api_key="EMPTY",
        model=cfg.model,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )


def _build_messages(state: AgentState) -> list:
    system = SystemMessage(content=(
        "你是港口仓储系统的意图分类器。判断用户输入属于哪一类，只能二选一：\n"
        f"- {BUSINESS}：与备件库存查询、出入库（出库/入库/调库）等仓储业务相关\n"
        f"- {GENERAL}：闲聊、与仓储业务无关、或无法识别的输入\n"
        "只返回 category 与简短 reason。"
    ))
    human = HumanMessage(content=f"用户输入：{state.user_input or '（图片输入）'}")
    return [system, human]


def classify_intent(state: AgentState) -> str:
    """第1层意图分类。LLM 失败或非法输出时兜底为 business（不拒正常业务）。"""
    # 纯图片输入默认 business（多为领料单/库存单据），不做多模态意图分类
    if state.image and not state.user_input:
        return BUSINESS
    try:
        llm = _get_intent_llm().with_structured_output(IntentDecision)
        decision = llm.invoke(_build_messages(state))
        if decision is not None and decision.category in (BUSINESS, GENERAL):
            return decision.category
    except Exception:
        pass
    return BUSINESS
