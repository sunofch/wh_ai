# src/api/models.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class InstructionRequest(BaseModel):
    text:         Optional[str] = None
    audio_base64: Optional[str] = None
    image_base64: Optional[str] = None


class ParsedInstruction(BaseModel):
    part_name:       Optional[str]  = None
    quantity:        Optional[int]  = None
    model:           Optional[str]  = None
    action_required: Optional[str]  = None
    is_urgent:       bool           = False
    description:     Optional[str]  = None


class InstructionResponse(BaseModel):
    instruction_id:    str
    status:            str
    vlm_available:     bool
    parsed:            ParsedInstruction
    resolved_location: str = ""
    target_port:       str = ""


class StatusResponse(BaseModel):
    queue_size:       int
    last_run_id:      Optional[str]      = None
    last_run_at:      Optional[datetime] = None
    scheduler_status: str = "idle"


class ScheduleResult(BaseModel):
    run_id:          str
    order_count:     int
    makespan:        int
    total_distance:  int
    agv_utilization: float
    planning_time:   float
    instructions:    list[str] = []
