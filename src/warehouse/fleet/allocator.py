# src/warehouse/fleet/allocator.py
"""位置感知贪心任务分配"""

from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.warehouse.fleet.pathfinding import PathFinder
    from src.warehouse.fleet.tsp import TSPSolver
    from src.warehouse.wms.config import WarehouseConfig
    from src.warehouse.models import TaskCluster, AGVState


class TaskAllocator:
    def __init__(self, path_finder: PathFinder, tsp: TSPSolver, config: WarehouseConfig):
        self.path_finder = path_finder
        self.tsp = tsp
        self.config = config

    def _calc_cluster_time(self, cluster: TaskCluster, agv_pos: tuple[int, int],
                           zone_pos: dict[str, tuple[int, int]]) -> tuple[int, tuple[int, int]]:
        """用 TSP 计算簇执行时间，返回 (估算时间, 簇出口位置)"""
        sorted_tasks, total_dist = self.tsp.optimize(cluster.tasks, agv_pos, zone_pos)
        c = self.config
        n_tasks = len(sorted_tasks)

        move_time = total_dist * c.AGV_MOVE_TIME
        load_time = n_tasks * 2 * c.AGV_LOAD_UNLOAD_TIME

        exit_pos = zone_pos.get(sorted_tasks[-1].dest, agv_pos) if sorted_tasks else agv_pos
        return move_time + load_time, exit_pos

    def allocate(self, clusters: list[TaskCluster], agv_states: list[AGVState],
                 zone_pos: dict[str, tuple[int, int]]) -> dict[int, list[TaskCluster]]:
        return self._greedy_allocate(clusters, agv_states, zone_pos)

    def _greedy_allocate(self, clusters: list[TaskCluster], agv_states: list[AGVState],
                         zone_pos: dict[str, tuple[int, int]]) -> dict[int, list[TaskCluster]]:
        """位置感知贪心：跟踪AGV出口位置，argmin(总分)选最优AGV"""
        result: dict[int, list[TaskCluster]] = defaultdict(list)
        agv_positions = {s.agv_id: s.init_pos for s in agv_states}
        agv_times = {s.agv_id: 0 for s in agv_states}

        sorted_clusters = sorted(clusters, key=lambda c: (-c.priority, -c.task_num))
        for cluster in sorted_clusters:
            best_agv = None
            best_score = float('inf')
            for agv in agv_states:
                cluster_time, exit_pos = self._calc_cluster_time(
                    cluster, agv_positions[agv.agv_id], zone_pos
                )
                score = agv_times[agv.agv_id] + cluster_time
                if score < best_score:
                    best_score = score
                    best_agv = agv.agv_id
                    best_exit = exit_pos
                    best_time = cluster_time

            result[best_agv].append(cluster)
            agv_times[best_agv] += best_time
            agv_positions[best_agv] = best_exit

        return result
