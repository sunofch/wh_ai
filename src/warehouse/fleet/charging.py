# src/warehouse/fleet/charging.py
"""充电感知调度"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.warehouse.fleet.pathfinding import PathFinder
    from src.warehouse.fleet.map_builder import WarehouseMap
    from src.warehouse.wms.config import WarehouseConfig


class ChargingScheduler:
    def __init__(self, path_finder: PathFinder, warehouse_map: WarehouseMap,
                 config: WarehouseConfig):
        self.path_finder = path_finder
        self.wmap = warehouse_map
        self.config = config

    def plan_charging(self, current_pos: tuple[int, int],
                      current_t: int) -> tuple[list[tuple[int, int]], int, tuple[int, int]]:
        """返回 (到充电桩的路径, 充电完成时间, 充电桩位置)"""
        # 找最近的充电桩
        nearest = min(
            self.wmap.charging_points,
            key=lambda p: self.path_finder.get_distance(current_pos, p),
        )
        path, _, time_cost = self.path_finder.find_path(
            current_pos, nearest, 0, 0, current_t, -1
        )
        charge_end_t = current_t + time_cost + self.config.AGV_CHARGE_TIME
        return path, charge_end_t, nearest

    def estimate_battery_usage(self, path_length: int) -> int:
        return path_length * self.config.AGV_CONSUME_RATE

    def need_charge(self, battery: int, estimated_usage: int) -> bool:
        return (battery - estimated_usage) < self.config.AGV_LOW_BATTERY_THRESHOLD
