# src/warehouse/fleet/fleet_manager.py
"""Fleet层总调度编排（路线A：保持簇边界 + 簇间TSP排序）"""

from __future__ import annotations
from typing import TYPE_CHECKING

from src.warehouse.models import AGVState, TaskCluster, TransportTask
from src.warehouse.fleet.pathfinding import PathFinder
from src.warehouse.fleet.tsp import TSPSolver
from src.warehouse.fleet.allocator import TaskAllocator

if TYPE_CHECKING:
    from src.warehouse.fleet.map_builder import WarehouseMap
    from src.warehouse.wms.config import WarehouseConfig


def _centroid(positions: list[tuple[int, int]]) -> tuple[int, int]:
    if not positions:
        return (0, 0)
    x = sum(p[0] for p in positions) / len(positions)
    y = sum(p[1] for p in positions) / len(positions)
    return (int(round(x)), int(round(y)))


class FleetManager:
    def __init__(self, warehouse_map: WarehouseMap, config: WarehouseConfig):
        self.wmap = warehouse_map
        self.config = config
        self.path_finder = PathFinder(warehouse_map, config)
        self.tsp = TSPSolver(self.path_finder, config)
        self.allocator = TaskAllocator(self.path_finder, self.tsp, config)

    def schedule(self, clusters: list[TaskCluster]) -> tuple[dict[int, list[TransportTask]], int]:
        """调度入口：贪心分配 → 簇间TSP排序 → 逐簇TSP排序"""
        # 1. 创建AGV状态
        agv_states = [
            AGVState(agv_id=i + 1, init_pos=pos, current_pos=pos)
            for i, pos in enumerate(self.wmap.config.agv_init_positions)
        ]

        # 2. 贪心分配
        allocation, makespan = self.allocator.allocate(
            clusters, agv_states, self.wmap.zone_pos
        )

        # 3. 逐簇TSP + 簇间排序
        agv_tasks: dict[int, list[TransportTask]] = {}
        for agv in agv_states:
            assigned_clusters = allocation.get(agv.agv_id, [])
            if not assigned_clusters:
                agv_tasks[agv.agv_id] = []
                continue

            if self.config.ablation.enable_tsp:
                # 簇间 OR-Tools TSP 排序
                if len(assigned_clusters) > 1:
                    cluster_order = self._sort_clusters_tsp(
                        assigned_clusters, agv.init_pos, self.wmap.zone_pos
                    )
                else:
                    cluster_order = list(assigned_clusters)

                # 逐簇 TSP 排序
                sorted_tasks: list[TransportTask] = []
                current_pos = agv.init_pos
                for cluster in cluster_order:
                    cluster_sorted, _ = self.tsp.optimize(
                        cluster.tasks, current_pos, self.wmap.zone_pos
                    )
                    sorted_tasks.extend(cluster_sorted)
                    # 更新位置到簇的出口（最后一个任务的 dest）
                    if cluster_sorted:
                        current_pos = self.wmap.zone_pos.get(
                            cluster_sorted[-1].dest, current_pos
                        )

                agv_tasks[agv.agv_id] = sorted_tasks
            else:
                all_tasks: list[TransportTask] = []
                for cluster in assigned_clusters:
                    all_tasks.extend(cluster.tasks)
                agv_tasks[agv.agv_id] = sorted(all_tasks, key=lambda t: -t.priority)

        return agv_tasks, makespan

    def _sort_clusters_tsp(self, clusters: list[TaskCluster],
                           agv_pos: tuple[int, int],
                           zone_pos: dict[str, tuple[int, int]]) -> list[TaskCluster]:
        """OR-Tools TSP 排簇的执行顺序"""
        n = len(clusters)

        # 计算每个簇的入口（pick质心）和出口（dest质心）
        entries = []
        exits = []
        for cluster in clusters:
            picks = [zone_pos.get(t.pick, agv_pos) for t in cluster.tasks]
            dests = [zone_pos.get(t.dest, agv_pos) for t in cluster.tasks]
            entries.append(_centroid(picks))
            exits.append(_centroid(dests))

        # 构建距离矩阵 (n+1 × n+1, depot=0)
        size = n + 1
        matrix = [[0] * size for _ in range(size)]

        for j in range(n):
            matrix[0][j + 1] = self.path_finder.get_distance(agv_pos, entries[j])

        for i in range(n):
            for j in range(n):
                if i != j:
                    matrix[i + 1][j + 1] = self.path_finder.get_distance(
                        exits[i], entries[j]
                    )

        # 复用 TSPSolver 底层求解器
        order = self.tsp._solve_tsp(matrix, n)
        return [clusters[i] for i in order]

    def precompute(self):
        """预计算所有关键路径"""
        self.path_finder.precompute_all_paths()
