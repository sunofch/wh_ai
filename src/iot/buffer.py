"""线程安全时序环形缓冲。

按 (equipment_id, metric) 维护定长序列，供动态因果图（causal.py）、
需求预测（pipeline.py）等模块以 numpy 数组消费。
"""
from __future__ import annotations

import threading
from collections import defaultdict, deque

import numpy as np

from src.iot.schemas import SensorReading

DEFAULT_MAXLEN = 4096


class TimeSeriesBuffer:
    """多路时序环形缓冲；append 与读取均加锁，可被采集线程并发写入。"""

    def __init__(self, maxlen: int = DEFAULT_MAXLEN):
        if maxlen <= 0:
            raise ValueError(f"maxlen must be positive, got {maxlen}")
        self._maxlen = maxlen
        self._lock = threading.Lock()
        self._series: dict[tuple[str, str], deque[float]] = defaultdict(
            lambda: deque(maxlen=self._maxlen)
        )

    def append(self, reading: SensorReading) -> None:
        with self._lock:
            self._series[(reading.equipment_id, reading.metric)].append(reading.value)

    def series(self, equipment_id: str, metric: str) -> np.ndarray:
        """某设备某指标的时序快照（旧→新）。"""
        with self._lock:
            values = self._series.get((equipment_id, metric))
            return np.array(values if values else [], dtype=np.float64)

    def as_dict(self, equipment_id: str, metrics: list[str]) -> dict[str, np.ndarray]:
        """多指标快照，可直接作为 DynamicCausalGraph.fit/update 的输入。"""
        return {metric: self.series(equipment_id, metric) for metric in metrics}

    def keys(self) -> list[tuple[str, str]]:
        with self._lock:
            return sorted(self._series)
