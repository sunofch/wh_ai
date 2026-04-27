# src/warehouse/simulation/simulator.py
"""仿真执行引擎"""

from __future__ import annotations
from typing import TYPE_CHECKING

from src.warehouse.models import (
    TransportTask, SimulationResult, TaskType, AGVStatus,
)
from src.warehouse.simulation.agv import AGV
from src.warehouse.fleet.charging import ChargingScheduler

if TYPE_CHECKING:
    from src.warehouse.fleet.fleet_manager import FleetManager
    from src.warehouse.fleet.map_builder import WarehouseMap
    from src.warehouse.wms.config import WarehouseConfig


class Simulator:
    def __init__(self, warehouse_map: WarehouseMap, fleet: FleetManager,
                 config: WarehouseConfig):
        self.wmap = warehouse_map
        self.fleet = fleet
        self.config = config
        self.charging = ChargingScheduler(fleet.path_finder, warehouse_map, config)

    def run(self, agv_tasks: dict[int, list[TransportTask]],
            estimated_makespan: int) -> SimulationResult:
        """执行仿真：遍历每个AGV的任务列表，生成轨迹"""
        import time as _time
        start = _time.time()

        max_steps = 15000
        agvs = [
            AGV(agv_id=i + 1, init_pos=pos, max_steps=max_steps)
            for i, pos in enumerate(self.wmap.config.agv_init_positions)
        ]
        self._agvs = agvs  # 存储供可视化使用

        for agv in agvs:
            tasks = agv_tasks.get(agv.agv_id, [])
            agv.assigned_tasks = tasks

        # 执行每个AGV的轨迹
        actual_makespan = 0
        for agv in agvs:
            end_t = self._execute_agv(agv)
            actual_makespan = max(actual_makespan, end_t)

        planning_time = _time.time() - start

        # 收集指标
        from src.warehouse.simulation.metrics import MetricsCollector
        result = MetricsCollector.collect(
            agvs, actual_makespan, planning_time, self.fleet.path_finder.st_table
        )
        return result

    def get_agvs(self) -> list[AGV]:
        """获取仿真后的AGV对象列表"""
        return self._agvs

    def _execute_agv(self, agv: AGV) -> int:
        current_pos = agv.current_pos
        current_dir = 0  # DIR_Y
        current_t = 0
        c = self.config

        for task in agv.assigned_tasks:
            # 充电检查
            if agv.battery < c.AGV_LOW_BATTERY_THRESHOLD:
                path, charge_end_t, charge_pos = self.charging.plan_charging(
                    current_pos, current_t
                )
                current_t = agv.record_path(path, current_t, "moving_to_charge", -1)
                current_t = agv.record_wait(
                    charge_pos, current_t, c.AGV_CHARGE_TIME, "charging", -1
                )
                agv.charge_full()
                current_pos = charge_pos

            pick_pos = self.wmap.zone_pos.get(task.pick, current_pos)
            dest_pos = self.wmap.zone_pos.get(task.dest, current_pos)

            # 移动到取货点
            path1, _, _ = self.fleet.path_finder.find_path(
                current_pos, pick_pos, 0, current_dir, current_t, agv.agv_id
            )
            current_t = agv.record_path(path1, current_t, "moving_empty", task.task_id)
            agv.consume_battery(len(path1))
            current_t = agv.record_wait(
                pick_pos, current_t, c.AGV_LOAD_UNLOAD_TIME, "loading", task.task_id
            )
            current_pos = pick_pos
            if len(path1) > 1:
                dx = path1[-1][0] - path1[-2][0]
                current_dir = 0 if dx != 0 else 1

            # 移动到卸货点
            path2, _, _ = self.fleet.path_finder.find_path(
                current_pos, dest_pos, 1, current_dir, current_t, agv.agv_id
            )
            current_t = agv.record_path(path2, current_t, "moving_loaded", task.task_id)
            agv.consume_battery(len(path2))
            current_t = agv.record_wait(
                dest_pos, current_t, c.AGV_LOAD_UNLOAD_TIME, "unloading", task.task_id
            )
            current_pos = dest_pos
            if len(path2) > 1:
                dx = path2[-1][0] - path2[-2][0]
                current_dir = 0 if dx != 0 else 1

            agv.completed_count += 1

        # 填充idle到max_steps
        agv.record_wait(current_pos, current_t, 1, "idle", -1)
        agv.total_time = current_t
        return current_t
