# src/warehouse/fleet/fleet_manager.py
"""Fleet层总调度编排"""

from __future__ import annotations
from typing import TYPE_CHECKING

from src.warehouse.models import AGVState, TaskCluster, TransportTask
from src.warehouse.fleet.pathfinding import PathFinder
from src.warehouse.fleet.tsp import TSPSolver
from src.warehouse.fleet.allocator import TaskAllocator

if TYPE_CHECKING:
    from src.warehouse.fleet.map_builder import WarehouseMap
    from src.warehouse.wms.config import WarehouseConfig


class FleetManager:
    def __init__(self, warehouse_map: WarehouseMap, config: WarehouseConfig):
        self.wmap = warehouse_map
        self.config = config
        self.path_finder = PathFinder(warehouse_map, config)
        self.tsp = TSPSolver(self.path_finder, config)
        self.allocator = TaskAllocator(self.path_finder, self.tsp, config)

    def schedule(self, clusters: list[TaskCluster]) -> tuple[dict[int, list[TransportTask]], int]:
        """调度入口：分配+TSP排序，返回 (agv_id→任务列表, makespan估计)"""
        # 1. 创建AGV状态
        agv_states = [
            AGVState(agv_id=i + 1, init_pos=pos, current_pos=pos)
            for i, pos in enumerate(self.wmap.config.agv_init_positions)
        ]

        # 2. CP-SAT分配
        allocation, makespan = self.allocator.allocate(
            clusters, agv_states, self.wmap.zone_pos
        )

        # 3. TSP排序每个AGV的任务
        agv_tasks: dict[int, list[TransportTask]] = {}
        for agv in agv_states:
            assigned_clusters = allocation.get(agv.agv_id, [])
            all_tasks: list[TransportTask] = []
            for cluster in assigned_clusters:
                all_tasks.extend(cluster.tasks)
            if all_tasks and self.config.ablation.enable_tsp:
                sorted_tasks, _ = self.tsp.optimize(
                    all_tasks, agv.init_pos, self.wmap.zone_pos
                )
                agv_tasks[agv.agv_id] = sorted_tasks
            else:
                agv_tasks[agv.agv_id] = sorted(all_tasks, key=lambda t: -t.priority)

        return agv_tasks, makespan

    def precompute(self):
        """预计算所有关键路径"""
        self.path_finder.precompute_all_paths()
