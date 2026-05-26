"""Supervisor：两步 LLM 流水线，只负责理解指令和创建工单。

流水线：
  instruction_agent（解析指令 → list[ParsedInstruction] JSON）
      ↓ 每条独立调用
  inventory_agent（查库存 + 建工单）
      ↓ 合并为单个 WorkOrder
  返回 WorkOrder

AGV 调度不在此处发生，由 scheduler_loop 触发 agv_agent 独立执行。
"""
from __future__ import annotations

import json
from typing import Any

from src.agents.instruction_agent import get_instruction_agent
from src.agents.inventory_agent import get_inventory_agent
from src.agents.work_order_assembler import print_agent_messages
from src.warehouse.models import OrderPriority, WorkOrder


def _extract_last_text(result: dict) -> str:
    """从 Agent 结果中提取最后一条消息的文本内容。"""
    messages = result.get("messages", [])
    if not messages:
        return ""
    content = messages[-1].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                return part.get("text", "")
    return str(content)


def _merge_work_orders(orders: list[WorkOrder]) -> WorkOrder:
    """将多个 WorkOrder 合并为一个，取最高优先级，合并所有 items。"""
    if not orders:
        return WorkOrder(order_id=0, source="vlm", priority=OrderPriority.NORMAL)
    if len(orders) == 1:
        return orders[0]

    merged_priority = max(o.priority for o in orders)
    merged_metadata: dict = {}
    for o in orders:
        merged_metadata.update(o.metadata)

    all_items = [item for o in orders for item in o.items]
    renumbered = [item.model_copy(update={"item_id": i + 1}) for i, item in enumerate(all_items)]

    return WorkOrder(
        order_id=orders[0].order_id,
        source="vlm",
        priority=merged_priority,
        items=renumbered,
        metadata=merged_metadata,
    )


def run(
    text: str | None = None,
    image: str | None = None,
    verbose: bool = False,
) -> WorkOrder:
    """Supervisor 主入口。返回合并后的单个 WorkOrder，不涉及 AGV 调度。"""
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

    # Step 1: instruction_agent — 解析指令，返回 list[ParsedInstruction] JSON
    result1 = get_instruction_agent().invoke(
        {"messages": [{"role": "user", "content": content}]}
    )
    if verbose:
        print_agent_messages(result1.get("messages", []))

    parsed_text = _extract_last_text(result1)
    try:
        parsed_list = json.loads(parsed_text)
        if not isinstance(parsed_list, list):
            parsed_list = [parsed_list]
    except (json.JSONDecodeError, TypeError):
        parsed_list = [{"raw": parsed_text}]

    # Step 2: inventory_agent — 每条独立查库存建工单，最后合并
    inventory_agent = get_inventory_agent()
    work_orders = [
        inventory_agent.run(json.dumps(item, ensure_ascii=False))
        for item in parsed_list
    ]
    return _merge_work_orders(work_orders)
