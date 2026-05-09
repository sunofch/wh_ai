# src/warehouse/fleet/allocator.py
"""位置感知贪心任务分配

核心思路:
  1. 按簇优先级降序遍历所有簇
  2. 对每个簇, 用TSP精确计算每个AGV执行该簇的预估时间
  3. 选择使"AGV累计时间 + 簇执行时间"最小的AGV
  4. 更新AGV的出口位置(簇最后一个任务的dest), 供后续簇使用
"""

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
        """用 TSP 排序后精确计算簇执行代价

        代价 = 移动距离 × move_time + 装卸次数 × load_time + 转弯 + 加速段
        返回 (总代价, 簇出口位置)
        """
        sorted_tasks, total_dist = self.tsp.optimize(cluster.tasks, agv_pos, zone_pos)
        c = self.config
        n_tasks = len(sorted_tasks)

        move_time = total_dist * c.AGV_MOVE_TIME
        load_time = n_tasks * 2 * c.AGV_LOAD_UNLOAD_TIME

        # 从TSP排序后的位置序列估算转弯和加速
        waypoints = [agv_pos]
        for t in sorted_tasks:
            waypoints.append(zone_pos.get(t.pick, agv_pos))
            waypoints.append(zone_pos.get(t.dest, agv_pos))

        turns = 0
        segments = 0
        prev_axis = None
        for i in range(1, len(waypoints)):
            if waypoints[i] == waypoints[i - 1]:
                continue
            segments += 1
            dx = waypoints[i][0] - waypoints[i - 1][0]
            dy = waypoints[i][1] - waypoints[i - 1][1]
            axis = 'x' if dx != 0 else 'y'
            if prev_axis is not None and axis != prev_axis:
                turns += 1
            prev_axis = axis

        exit_pos = zone_pos.get(sorted_tasks[-1].dest, agv_pos) if sorted_tasks else agv_pos
        return move_time + load_time + turns * c.AGV_TURN_TIME + segments * c.AGV_ACCEL_TIME, exit_pos

    def allocate(self, clusters: list[TaskCluster], agv_states: list[AGVState],
                 zone_pos: dict[str, tuple[int, int]]) -> dict[int, list[TaskCluster]]:
        """分配入口: 返回 {agv_id: [assigned_clusters]}"""
        return self._greedy_allocate(clusters, agv_states, zone_pos)

    def _greedy_allocate(self, clusters: list[TaskCluster], agv_states: list[AGVState],
                         zone_pos: dict[str, tuple[int, int]]) -> dict[int, list[TaskCluster]]:
        """位置感知贪心分配

        按簇优先级降序遍历, 每个簇选择使其累计完成时间最小的AGV。
        跟踪每个AGV的出口位置, 使后续簇能感知AGV的实际位置。
        """
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
