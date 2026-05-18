"""Agent 3：AGV 调度 Agent（AGV Scheduling Agent）。

职责：
  1. 从对话历史中提取 inventory_agent 创建的工单数据
  2. 调用 schedule_agv_tasks 执行调度规划
  3. 返回各 AGV 的任务分配结果
"""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.agent.tools.agv_tool import schedule_agv_tasks
from src.common.config import config

AGENT_NAME = "agv_agent"

_SYSTEM_PROMPT = """你是港口备件仓储系统的 AGV 调度专家。

收到工单信息后，按以下步骤处理：
1. 从对话历史中找到工单数据（JSON 格式，含 order_id、priority、items 字段）
2. 将完整工单 JSON 传入 schedule_agv_tasks 工具执行调度规划
3. 返回调度结果摘要

最终以 JSON 格式返回：
{
  "scheduling_status": "completed" | "failed",
  "agv_count": <参与调度的 AGV 数量>,
  "total_tasks": <总任务数>,
  "assignments": { "agv_1": [...], "agv_2": [...] }
}
"""


@lru_cache(maxsize=1)
def get_agv_agent():
    """返回编译好的 AGV 调度 ReAct Agent。"""
    port = config.vllm_server.base_port + 1
    host = config.vllm_server.host
    llm = ChatOpenAI(
        base_url=f"http://{host}:{port}/v1",
        api_key="EMPTY",
        model=config.supervisor.model,
        temperature=0,
        max_tokens=config.supervisor.max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return create_react_agent(
        llm,
        [schedule_agv_tasks],
        prompt=_SYSTEM_PROMPT,
        name=AGENT_NAME,
    )
