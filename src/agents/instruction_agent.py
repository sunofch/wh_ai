"""Agent 1：领料解析 Agent（Instruction Parsing Agent）。

提供 get_instruction_agent() 供 Supervisor 直接挂载。

图结构：
  entity_extract → field_validator →
    need_rag  → prepare_rag_query → tools → call_model_final → END
    complete  →                            call_model_final → END
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import ValidationError

from src.agent_tools.knowledge_tool import query_knowledge_base
from src.agents.schemas import ParsedInstruction
from src.common.config import config
from src.common.prompts import load_prompts

AGENT_NAME = "instruction_agent"


class InstructionState(TypedDict):
    messages: Annotated[list, add_messages]
    entities: list  # entity_extract 写入，每个元素为一个备件 dict
    route: str      # field_validator 写入：need_rag / complete


def _parse_and_validate(text: str) -> list[ParsedInstruction]:
    """从模型输出中提取 JSON 数组并用 Pydantic 逐条校验。"""
    raw = None
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                raw = json.loads(match.group())
            except json.JSONDecodeError:
                pass
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        try:
            result.append(ParsedInstruction(**item))
        except (ValidationError, TypeError):
            pass
    return result


@lru_cache(maxsize=1)
def get_instruction_agent():
    """返回编译好的领料解析图（LangGraph CompiledGraph）。"""
    port = config.vllm_server.base_port + 1
    host = config.vllm_server.host
    base_url = f"http://{host}:{port}/v1"
    common_kwargs = dict(
        base_url=base_url,
        api_key="EMPTY",
        temperature=0,
        max_tokens=config.vlm35.max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    llm_base = ChatOpenAI(model=config.vlm35.model, **common_kwargs)
    llm_lora = ChatOpenAI(
        model=config.vlm35.lora_adapter_name or config.vlm35.model,
        **common_kwargs,
    )

    _prompts = load_prompts()["instruction_agent"]
    extract_sys = SystemMessage(content=_prompts["extract"])
    final_sys = SystemMessage(content=_prompts["final"])

    # ── 节点 ──────────────────────────────────────────────────

    def entity_extract(state: InstructionState) -> dict:
        """输入 messages，调 llm_lora 抽取实体列表，输出 entities list。"""
        response = llm_lora.invoke([extract_sys] + state["messages"])
        try:
            entities = json.loads(response.content)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", response.content, re.DOTALL)
            try:
                entities = json.loads(match.group()) if match else []
            except json.JSONDecodeError:
                entities = []
        if isinstance(entities, dict):
            entities = [entities]
        return {"entities": entities if isinstance(entities, list) else []}

    def field_validator(state: InstructionState) -> dict:
        """输入 entities list，任一备件 model 为 null 则走 RAG。不调 LLM。"""
        entities = state.get("entities", [])
        if any(e.get("model") is None for e in entities):
            return {"route": "need_rag"}
        return {"route": "complete"}

    def prepare_rag_query(state: InstructionState) -> dict:
        """对每个 model 为 null 的备件构造一条 tool_call。"""
        entities = state.get("entities", [])
        tool_calls = [
            {
                "id": f"rag_call_{i}",
                "name": "query_knowledge_base",
                "args": {"query": e.get("part_name", ""), "top_k": 3},
            }
            for i, e in enumerate(entities)
            if e.get("model") is None
        ]
        return {"messages": [AIMessage(content="", tool_calls=tool_calls)]}

    def call_model_final(state: InstructionState) -> dict:
        """输入 entities hint + HumanMessage + ToolMessage，调 llm_lora 输出 JSON 数组。"""
        entities = state.get("entities", [])
        entity_hint = HumanMessage(
            content=f"已提取实体列表（供参考）：{json.dumps(entities, ensure_ascii=False)}"
        )
        # 过滤掉中间 AIMessage（tool_call 决策），保留用户消息和工具结果
        context = [m for m in state["messages"] if not isinstance(m, AIMessage)]
        response = llm_lora.invoke([final_sys, entity_hint] + context)
        orders = _parse_and_validate(response.content)
        return {"messages": [AIMessage(content=json.dumps(
            [o.model_dump() for o in orders], ensure_ascii=False
        ))]}

    def route_after_validation(state: InstructionState) -> str:
        return state.get("route", "complete")

    # ── 图构建 ────────────────────────────────────────────────

    graph = StateGraph(InstructionState)
    graph.add_node("entity_extract", entity_extract)
    graph.add_node("field_validator", field_validator)
    graph.add_node("prepare_rag_query", prepare_rag_query)
    graph.add_node("tools", ToolNode([query_knowledge_base]))
    graph.add_node("call_model_final", call_model_final)

    graph.add_edge(START, "entity_extract")
    graph.add_edge("entity_extract", "field_validator")
    graph.add_conditional_edges("field_validator", route_after_validation, {
        "need_rag": "prepare_rag_query",
        "complete": "call_model_final",
    })
    graph.add_edge("prepare_rag_query", "tools")
    graph.add_edge("tools", "call_model_final")
    graph.add_edge("call_model_final", END)

    return graph.compile()
