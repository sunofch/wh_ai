"""CSV 历史数据回放：无 MQTT broker 环境的兜底采集源。

CSV 列约定：sensor_id, equipment_id, metric, value, ts。
坏行跳过并记日志，不中断回放。
"""
from __future__ import annotations

import csv
import logging

from pydantic import ValidationError

from src.iot.buffer import TimeSeriesBuffer
from src.iot.schemas import SensorReading

logger = logging.getLogger(__name__)


def replay_csv(csv_path: str, buffer: TimeSeriesBuffer) -> int:
    """把 CSV 中的传感读数写入缓冲区，返回成功条数。"""
    count = 0
    with open(csv_path, encoding="utf-8") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            try:
                reading = SensorReading(**row)
            except (ValidationError, TypeError) as exc:
                logger.warning("%s:%d 行无法解析，已跳过: %s", csv_path, line_no, exc)
                continue
            buffer.append(reading)
            count += 1
    return count
