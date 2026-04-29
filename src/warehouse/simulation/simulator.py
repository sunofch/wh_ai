# src/warehouse/simulation/simulator.py
"""仿真执行引擎（支持双向batch：OUTBOUND多取一送 + INBOUND一取多送）"""

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
        self._agvs = agvs

        for agv in agvs:
            tasks = agv_tasks.get(agv.agv_id, [])
            agv.assigned_tasks = tasks

        actual_makespan = 0
        for agv in agvs:
            end_t = self._execute_agv(agv)
            actual_makespan = max(actual_makespan, end_t)

        planning_time = _time.time() - start

        from src.warehouse.simulation.metrics import MetricsCollector
        result = MetricsCollector.collect(
            agvs, actual_makespan, planning_time, self.fleet.path_finder.st_table
        )
        return result

    def get_agvs(self) -> list[AGV]:
        """获取仿真后的AGV对象列表"""
        return self._agvs

    def _detect_batch(self, tasks: list[TransportTask], i: int) -> tuple[str, int]:
        """检测从位置 i 开始的 batch 类型

        Returns: (batch_type, batch_end)
          - ("outbound", end): 连续同 dest → 多取一送
          - ("inbound", end):  连续同 pick → 一取多送
          - ("single", i+1):  单任务
        """
        # 1. 检查连续同 dest（OUTBOUND batch）
        dest = tasks[i].dest
        end = i + 1
        while end < len(tasks) and tasks[end].dest == dest:
            end += 1
        if end - i > 1:
            return "outbound", end

        # 2. 检查连续同 pick（INBOUND batch）
        pick = tasks[i].pick
        end = i + 1
        while end < len(tasks) and tasks[end].pick == pick:
            end += 1
        if end - i > 1:
            return "inbound", end

        # 3. 单任务
        return "single", i + 1

    def _update_dir(self, path, current_dir):
        """从路径最后两步更新方向"""
        if len(path) > 1:
            dx = path[-1][0] - path[-2][0]
            return 0 if dx != 0 else 1
        return current_dir

    def _execute_agv(self, agv: AGV) -> int:
        """执行AGV任务：自动检测 batch 类型并分模式执行"""
        current_pos = agv.current_pos
        current_dir = 0
        current_t = 0
        c = self.config
        tasks = agv.assigned_tasks
        pf = self.fleet.path_finder

        i = 0
        while i < len(tasks):
            # 充电检查
            if agv.battery < c.AGV_LOW_BATTERY_THRESHOLD:
                path, _, charge_pos = self.charging.plan_charging(
                    current_pos, current_t
                )
                current_t = agv.record_path(path, current_t, "moving_to_charge", -1)
                current_t = agv.record_wait(
                    charge_pos, current_t, c.AGV_CHARGE_TIME, "charging", -1
                )
                agv.charge_full()
                current_pos = charge_pos

            batch_type, batch_end = self._detect_batch(tasks, i)

            if batch_type == "outbound":
                # ── OUTBOUND batch: [move→load]×N → move → unload×N ──
                batch = tasks[i:batch_end]
                dest_pos = self.wmap.zone_pos.get(batch[0].dest, current_pos)

                for task in batch:
                    pick_pos = self.wmap.zone_pos.get(task.pick, current_pos)
                    path1, _, _ = pf.find_path(
                        current_pos, pick_pos, 0, current_dir, current_t, agv.agv_id
                    )
                    current_t = agv.record_path(path1, current_t, "moving_empty", task.task_id)
                    agv.consume_battery(len(path1))
                    current_pos = pick_pos
                    current_dir = self._update_dir(path1, current_dir)
                    current_t = agv.record_wait(
                        pick_pos, current_t, c.AGV_LOAD_UNLOAD_TIME, "loading", task.task_id
                    )

                path2, _, _ = pf.find_path(
                    current_pos, dest_pos, 1, current_dir, current_t, agv.agv_id
                )
                current_t = agv.record_path(path2, current_t, "moving_loaded", batch[0].task_id)
                agv.consume_battery(len(path2))
                current_pos = dest_pos
                current_dir = self._update_dir(path2, current_dir)

                for task in batch:
                    current_t = agv.record_wait(
                        dest_pos, current_t, c.AGV_LOAD_UNLOAD_TIME, "unloading", task.task_id
                    )
                    agv.completed_count += 1

            elif batch_type == "inbound":
                # ── INBOUND batch: move → load×N → [move→unload]×N ──
                batch = tasks[i:batch_end]
                pick_pos = self.wmap.zone_pos.get(batch[0].pick, current_pos)

                # A: 移动到 pick（空载）
                path0, _, _ = pf.find_path(
                    current_pos, pick_pos, 0, current_dir, current_t, agv.agv_id
                )
                current_t = agv.record_path(path0, current_t, "moving_empty", batch[0].task_id)
                agv.consume_battery(len(path0))
                current_pos = pick_pos
                current_dir = self._update_dir(path0, current_dir)

                # B: 批量取货
                for task in batch:
                    current_t = agv.record_wait(
                        pick_pos, current_t, c.AGV_LOAD_UNLOAD_TIME, "loading", task.task_id
                    )

                # C: 逐个送货
                for task in batch:
                    dest_pos = self.wmap.zone_pos.get(task.dest, current_pos)
                    path1, _, _ = pf.find_path(
                        current_pos, dest_pos, 1, current_dir, current_t, agv.agv_id
                    )
                    current_t = agv.record_path(path1, current_t, "moving_loaded", task.task_id)
                    agv.consume_battery(len(path1))
                    current_pos = dest_pos
                    current_dir = self._update_dir(path1, current_dir)
                    current_t = agv.record_wait(
                        dest_pos, current_t, c.AGV_LOAD_UNLOAD_TIME, "unloading", task.task_id
                    )
                    agv.completed_count += 1

            else:
                # ── 单任务: move→load → move→unload ──
                task = tasks[i]
                pick_pos = self.wmap.zone_pos.get(task.pick, current_pos)
                dest_pos = self.wmap.zone_pos.get(task.dest, current_pos)

                path1, _, _ = pf.find_path(
                    current_pos, pick_pos, 0, current_dir, current_t, agv.agv_id
                )
                current_t = agv.record_path(path1, current_t, "moving_empty", task.task_id)
                agv.consume_battery(len(path1))
                current_pos = pick_pos
                current_dir = self._update_dir(path1, current_dir)
                current_t = agv.record_wait(
                    pick_pos, current_t, c.AGV_LOAD_UNLOAD_TIME, "loading", task.task_id
                )

                path2, _, _ = pf.find_path(
                    current_pos, dest_pos, 1, current_dir, current_t, agv.agv_id
                )
                current_t = agv.record_path(path2, current_t, "moving_loaded", task.task_id)
                agv.consume_battery(len(path2))
                current_pos = dest_pos
                current_dir = self._update_dir(path2, current_dir)
                current_t = agv.record_wait(
                    dest_pos, current_t, c.AGV_LOAD_UNLOAD_TIME, "unloading", task.task_id
                )
                agv.completed_count += 1

            i = batch_end

        agv.record_wait(current_pos, current_t, 1, "idle", -1)
        agv.total_time = current_t
        return current_t
