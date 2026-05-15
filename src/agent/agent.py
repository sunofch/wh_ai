"""ReAct Agent：LangGraph create_react_agent 驱动端到端指令解析。"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.agent.tools.knowledge_tool import query_knowledge_base
from src.agent.tools.inventory_tool import query_inventory
from src.agent.tools.order_tool import create_restock
from src.common.config import config
from src.common.prompts import load_prompts
from src.warehouse.models import WorkOrder
from src.warehouse.wms.inventory_db import StockManager
from src.warehouse.wms.order_manager import OrderManager
from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401


@lru_cache(maxsize=1)
def _get_compiled_agent():
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
    return create_react_agent(llm, tools, prompt=system_prompt)


def run_agent(
    text: str | None = None,
    image: str | None = None,
    verbose: bool = False,
) -> WorkOrder:
    """Agent 主入口：接收原始文本/图片，返回可直接下发的 WorkOrder。"""
    agent = _get_compiled_agent()

    content: list[dict[str, Any]] = []
    if image:
        import base64
        from pathlib import Path
        img_b64 = base64.b64encode(Path(image).read_bytes()).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
        })
    if text:
        content.append({"type": "text", "text": text})
    if not content:
        content = [{"type": "text", "text": "无有效输入"}]

    result = agent.invoke({"messages": [{"role": "user", "content": content}]})

    if verbose:
        _print_agent_messages(result.get("messages", []))

    return _assemble_work_order(result)


def _print_agent_messages(messages: list) -> None:
    """将 Agent 消息链格式化输出，便于观测推理过程。"""
    from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
    sep = "─" * 50
    print(f"\n{'═' * 50}")
    print("  Agent 推理过程")
    print(f"{'═' * 50}")
    for msg in messages:
        if isinstance(msg, HumanMessage):
            # 跳过用户原始输入（通常含图片 base64，太长）
            continue
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", [])
            if tool_calls:
                print(f"\n[LLM → 调用工具]")
                for tc in tool_calls:
                    print(f"  工具: {tc['name']}")
                    print(f"  参数: {json.dumps(tc['args'], ensure_ascii=False)}")
            else:
                print(f"\n[LLM → 最终输出]")
                print(f"  {msg.content}")
        elif isinstance(msg, ToolMessage):
            print(f"\n[工具结果] {getattr(msg, 'name', '')}")
            try:
                parsed = json.loads(msg.content)
                print(f"  {json.dumps(parsed, ensure_ascii=False, indent=2)}")
            except Exception:
                print(f"  {msg.content}")
    print(f"{'═' * 50}\n")


def _assemble_work_order(agent_result: dict) -> WorkOrder:
    """从 Agent 返回的消息列表中提取字段和工具结果，组装 WorkOrder。"""
    from langchain_core.messages import ToolMessage

    messages = agent_result.get("messages", [])
    final_text = messages[-1].content if messages else ""

    instruction = _parse_instruction(final_text)

    inventory_result: dict | None = None
    for msg in messages:
        if isinstance(msg, ToolMessage) and getattr(msg, "name", "") == "query_inventory":
            try:
                inventory_result = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                pass

    map_cfg = MapRegistry.get("medium_57x47")
    db = StockManager()
    om = OrderManager(map_cfg)
    order = om.from_port_instruction(instruction, inventory_db=db)

    if order is None:
        from src.warehouse.models import OrderPriority
        order = WorkOrder(order_id=0, source="vlm", priority=OrderPriority.NORMAL)

    if (instruction is not None
            and instruction.action_required == "出库"
            and inventory_result is not None
            and not inventory_result.get("sufficient", True)
            and inventory_result.get("shortage", 0) > 0):
        restock = create_restock(
            model=instruction.model or "",
            part_name=instruction.part_name or "",
            shortage=inventory_result["shortage"],
            is_urgent=instruction.is_urgent,
        )
        order.metadata["restock_order_id"] = restock["order_id"]

    return order


def _parse_instruction(text: str):
    """从 Agent 最终输出文本中提取 PortInstruction。"""
    from src.parser.parser import PortInstruction, PortInstructionParser

    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return PortInstruction(**{
                k: v for k, v in data.items()
                if k in PortInstruction.model_fields
            })
    except Exception:
        pass

    return PortInstructionParser()._rule_based_parse(text)
