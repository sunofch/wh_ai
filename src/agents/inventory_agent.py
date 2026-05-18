"""Agent 2：库存管理 Agent（Inventory Management Agent）。

职责：
  1. 查询库存可用量
  2. 创建出入库工单
  3. 库存不足时自主触发补货
"""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.agent.tools.inventory_tool import query_inventory
from src.agent.tools.order_tool import create_work_order, create_restock_order
from src.common.config import config

AGENT_NAME = "inventory_agent"

_SYSTEM_PROMPT = """你是港口备件仓储系统的库存管理专家。

收到包含备件信息的请求时，按以下步骤处理：
1. 调用 query_inventory 查询库存可用量
2. 调用 create_work_order 创建对应的出库或入库工单
3. 如果 query_inventory 返回 sufficient=false，额外调用 create_restock_order 创建补货单

最终以 JSON 格式返回结果：
{
  "work_order_status": "created" | "failed",
  "restock_order_id": "RS-XXXX"
}
restock_order_id 仅在库存不足时包含。
"""


@lru_cache(maxsize=1)
def get_inventory_agent():
    """返回编译好的库存管理 ReAct Agent（LangGraph CompiledGraph）。"""
    port = config.vllm_server.base_port + 1
    host = config.vllm_server.host
    llm = ChatOpenAI(
        base_url=f"http://{host}:{port}/v1",
        api_key="EMPTY",
        model=config.inventory_agent.model,
        temperature=0,
        max_tokens=config.inventory_agent.max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    tools = [query_inventory, create_work_order, create_restock_order]
    return create_react_agent(
        llm,
        tools,
        prompt=_SYSTEM_PROMPT,
        name=AGENT_NAME,
    )
