# src/warehouse/wms/config.py
"""全局配置 — Pydantic Settings"""

from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from src.warehouse.models import AblationFlags


class WarehouseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WH_")

    # 地图
    MAP_NAME: str = "medium_50x50"

    # AGV运动参数
    AGV_MOVE_TIME: int = 1
    AGV_ACCEL_TIME: int = 2
    AGV_DECEL_TIME: int = 2
    AGV_TURN_TIME: int = 3
    AGV_LOAD_UNLOAD_TIME: int = 8

    # AGV电量参数
    AGV_MAX_BATTERY: int = 100
    AGV_CHARGE_RATE: int = 5
    AGV_CONSUME_RATE: int = 1
    AGV_CHARGE_TIME: int = 20
    AGV_LOW_BATTERY_THRESHOLD: int = 20

    # 任务参数
    AGV_MAX_TASK_CAPACITY: int = 20
    ORDER_NUM: int = 40
    MIN_SUBTASK_PER_ORDER: int = 2
    MAX_SUBTASK_PER_ORDER: int = 6
    CROSS_ZONE_ORDER_RATIO: float = 0.4

    # 求解器参数
    TSP_TIME_LIMIT: int = 1
    CP_SAT_TIME_LIMIT: int = 30
    A_MAX_SEARCH: int = 5000

    # 随机种子
    RANDOM_SEED: int = 42

    # 消融开关
    ablation: AblationFlags = AblationFlags()
