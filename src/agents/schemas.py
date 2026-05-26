"""Agent 结构化输出 Schema 定义。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ParsedInstruction(BaseModel):
    """instruction_agent 的结构化输出 schema。"""
    part_name: str
    model: Optional[str] = None
    quantity: Optional[int] = None
    action_required: Optional[str] = None
    is_urgent: bool = False
    description: Optional[str] = None
