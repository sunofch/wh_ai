"""传感读数统一结构。"""
from __future__ import annotations

from pydantic import BaseModel


class SensorReading(BaseModel):
    """一条传感读数。所有采集源（MQTT/OPC-UA/回放）统一为此结构。"""
    sensor_id: str
    equipment_id: str
    metric: str
    value: float
    ts: str
