"""Agent 结构化输出 Schema 定义。"""
from __future__ import annotations

from pydantic import BaseModel


class ParsedInstruction(BaseModel):
    """instruction_agent 的结构化输出 schema。"""
    part_name: str
    model: str | None = None
    quantity: int
    action_required: str
    is_urgent: bool = False
