"""Agent 1：领料解析 Agent（Instruction Parsing Agent）。

提供 get_instruction_agent() 供 Supervisor 直接挂载；
由 Supervisor 编排调用。

图结构：call_model → (有 tool_calls) → tools → call_model_final → END
                   → (无 tool_calls) → END
保证最多执行一次工具调用，物理断掉 ReAct 无限回路。
"""
from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.prebuilt import ToolNode

from src.agent_tools.knowledge_tool import query_knowledge_base
from src.agents.schemas import ParsedInstruction
from src.common.config import config
from src.common.prompts import load_prompts

AGENT_NAME = "instruction_agent"


@lru_cache(maxsize=1)
def get_instruction_agent():
    """返回编译好的领料解析自定义图（LangGraph CompiledGraph）。"""
    system_prompt = load_prompts()["instruction_agent"]["system"]
    port = config.vllm_server.base_port + 1
    host = config.vllm_server.host
    llm = ChatOpenAI(
        base_url=f"http://{host}:{port}/v1",
        api_key="EMPTY",
        model=config.vlm35.model,
        temperature=0,
        max_tokens=config.vlm35.max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    llm_with_tools = llm.bind_tools([query_knowledge_base])
    structured_llm = llm.with_structured_output(ParsedInstruction)
    sys_msg = SystemMessage(content=system_prompt)
    final_sys_msg = SystemMessage(content=(
        "根据对话历史和工具查询结果，提取并填写以下字段："
        "备件名（part_name）、型号（model）、数量（quantity）、"
        "操作类型（action_required：出库/入库/调库）、是否紧急（is_urgent）。"
    ))

    def call_model(state: MessagesState) -> dict:
        return {"messages": [llm_with_tools.invoke([sys_msg] + state["messages"])]}

    def call_model_final(state: MessagesState) -> dict:
        filtered = [m for m in state["messages"] if not isinstance(m, AIMessage)]
        result = structured_llm.invoke([final_sys_msg] + filtered)
        return {"messages": [AIMessage(content=result.model_dump_json())]}

    def route(state: MessagesState) -> str:
        return "tools" if state["messages"][-1].tool_calls else "call_model_final"

    graph = StateGraph(MessagesState)
    graph.add_node("call_model", call_model)
    graph.add_node("tools", ToolNode([query_knowledge_base]))
    graph.add_node("call_model_final", call_model_final)
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", route)
    graph.add_edge("tools", "call_model_final")
    graph.add_edge("call_model_final", END)

    return graph.compile()
