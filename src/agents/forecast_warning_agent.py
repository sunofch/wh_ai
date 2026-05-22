"""Agent 4：预测预警 Agent（Forecast Warning Agent）。"""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.agent_tools.forecast_warning_tool import analyze_inventory_risk
from src.common.config import config
from src.common.prompts import load_prompts

AGENT_NAME = "forecast_warning_agent"


@lru_cache(maxsize=1)
def get_forecast_warning_agent():
    """返回编译好的预测预警 ReAct Agent（LangGraph CompiledGraph）。"""
    port = config.vllm_server.base_port + 1
    host = config.vllm_server.host
    llm = ChatOpenAI(
        base_url=f"http://{host}:{port}/v1",
        api_key="EMPTY",
        model=config.forecast_warning_agent.model,
        temperature=0,
        max_tokens=config.forecast_warning_agent.max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    tools = [analyze_inventory_risk]
    return create_react_agent(
        llm,
        tools,
        prompt=load_prompts()["forecast_warning_agent"]["system"],
        name=AGENT_NAME,
    )
