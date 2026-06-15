"""意图识别层（第1层）。

由 LLM 把用户输入粗分为 business / general 两类：
  - business：库存查询、出入库等仓储业务 → 进 instruction_agent → inventory_agent 业务链
  - general ：闲聊 / 无关 / 无法识别 → general_reply_node 直接回复

第2层（query/order 细分）仍由 inventory_agent 内部的 _classify_intent 规则完成。
"""
from __future__ import annotations

import logging
from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.agents.state import AgentState
from src.common.config import config

logger = logging.getLogger(__name__)

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
        f"- {BUSINESS}：与备件库存查询、出入库（出库/入库/调库）、库存预警/风险分析等仓储业务相关\n"
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
        logger.warning("意图分类 LLM 返回非法类别: %r，兜底为 business", decision)
    except Exception:
        logger.warning("意图分类 LLM 调用失败，兜底为 business", exc_info=True)
    return BUSINESS


@lru_cache(maxsize=1)
def _get_reply_llm() -> ChatOpenAI:
    """general 回复用 LLM，温度略高以生成自然语言。"""
    cfg = config.supervisor
    host, port = _endpoint()
    return ChatOpenAI(
        base_url=f"http://{host}:{port}/v1",
        api_key="EMPTY",
        model=cfg.model,
        temperature=0.7,
        max_tokens=cfg.max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )


def general_reply(state: AgentState) -> str:
    """为 general 意图生成一句友好回复；LLM 不可用时退固定文案。"""
    try:
        system = SystemMessage(content=(
            "你是港口仓储备件管理系统的助手。用户的输入不是库存业务操作，"
            "请用一句友好的中文回应，并引导用户说出库存查询或出入库需求。"
        ))
        human = HumanMessage(content=state.user_input or "")
        resp = _get_reply_llm().invoke([system, human])
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        return text.strip() or FALLBACK_REPLY
    except Exception:
        logger.warning("general 回复 LLM 调用失败，使用固定兜底文案", exc_info=True)
        return FALLBACK_REPLY
