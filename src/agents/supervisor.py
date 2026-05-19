"""Supervisor：手动顺序编排三个子 Agent，最小化跨 Agent 的 context 传递。

流水线：
  instruction_agent（解析指令）
      ↓ 只传最后一条消息文本
  inventory_agent（查库存 + 建工单）
      ↓ 只传工单 JSON 文本
  agv_agent（调度 AGV）
"""
from __future__ import annotations

from typing import Any

from src.agents.instruction_agent import get_instruction_agent
from src.agents.inventory_agent import get_inventory_agent
from src.agents.agv_agent import get_agv_agent


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


def run(
    text: str | None = None,
    image: str | None = None,
    verbose: bool = False,
):
    """Supervisor 主入口。每个子 Agent 只接收上一步的最小输出，不累积完整历史。"""
    from src.agent.agent import _assemble_work_order, _print_agent_messages

    # 构建用户输入
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

    # Step 1: instruction_agent — 只接收原始用户输入
    result1 = get_instruction_agent().invoke(
        {"messages": [{"role": "user", "content": content}]}
    )
    if verbose:
        _print_agent_messages(result1.get("messages", []))
    parsed_text = _extract_last_text(result1)

    # Step 2: inventory_agent — 只接收 instruction_agent 的最终文本
    result2 = get_inventory_agent().invoke(
        {"messages": [{"role": "user", "content": parsed_text}]}
    )
    if verbose:
        _print_agent_messages(result2.get("messages", []))
    work_order_text = _extract_last_text(result2)

    # Step 3: agv_agent — 只接收工单 JSON 文本
    result3 = get_agv_agent().invoke(
        {"messages": [{"role": "user", "content": work_order_text}]}
    )
    if verbose:
        _print_agent_messages(result3.get("messages", []))

    # 用 inventory_agent 的 messages 组装 WorkOrder（含 create_work_order ToolMessage）
    return _assemble_work_order({"messages": result2.get("messages", [])})
