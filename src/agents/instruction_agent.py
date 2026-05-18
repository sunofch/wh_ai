"""Agent 1：领料解析 Agent（Instruction Parsing Agent）。

提供 get_instruction_agent() 供 Supervisor 直接挂载；
同时向后兼容 src.agent.agent 的单 Agent 调用路径。
"""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.agent.tools.knowledge_tool import query_knowledge_base
from src.agent.tools.inventory_tool import query_inventory
from src.common.config import config
from src.common.prompts import load_prompts

AGENT_NAME = "instruction_agent"


@lru_cache(maxsize=1)
def get_instruction_agent():
    """返回编译好的领料解析 ReAct Agent（LangGraph CompiledGraph）。"""
    system_prompt = load_prompts()["agent"]["system"]
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
    tools = [query_knowledge_base, query_inventory]
    return create_react_agent(
        llm,
        tools,
        prompt=system_prompt,
        name=AGENT_NAME,
    )
