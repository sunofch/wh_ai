"""ReAct Agent：LangGraph create_react_agent 驱动端到端指令解析。"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from src.warehouse.models import WorkOrder
from src.warehouse.wms.inventory_db import StockManager
from src.warehouse.wms.order_manager import OrderManager
from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401


@lru_cache(maxsize=1)
def _get_compiled_agent():
    from src.agents.instruction_agent import get_instruction_agent
    return get_instruction_agent()


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
    """从 Agent 返回的消息列表中提取字段和工具结果，组装 WorkOrder。

    向后扫描 AIMessage，找到最后一条含可解析 PortInstruction 的消息。
    兼容单 ReAct Agent 和 Supervisor 两种调用场景。
    """
    from langchain_core.messages import AIMessage, ToolMessage

    messages = agent_result.get("messages", [])

    instruction = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            text = msg.content if isinstance(msg.content, str) else ""
            instruction = _parse_instruction(text)
            if instruction is not None:
                break

    map_cfg = MapRegistry.get("medium_57x47")
    db = StockManager()
    om = OrderManager(map_cfg)
    order = om.from_port_instruction(instruction, inventory_db=db)

    if order is None:
        from src.warehouse.models import OrderPriority
        order = WorkOrder(order_id=0, source="vlm", priority=OrderPriority.NORMAL)

    # 从 inventory_agent 的工具调用结果中提取补货单号
    for msg in messages:
        if isinstance(msg, ToolMessage) and getattr(msg, "name", "") == "create_restock_order":
            try:
                restock_data = json.loads(msg.content)
                if restock_data.get("order_id"):
                    order.metadata["restock_order_id"] = restock_data["order_id"]
            except (json.JSONDecodeError, TypeError):
                pass

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
