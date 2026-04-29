# src/warehouse/fleet/allocator.py
"""CP-SAT全局任务分配 + 贪心降级"""

from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING

import numpy as np
from ortools.sat.python import cp_model

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
                           zone_pos: dict[str, tuple[int, int]]) -> int:
        sorted_tasks, total_dist = self.tsp.optimize(cluster.tasks, agv_pos, zone_pos)
        c = self.config

        # 统计 batch 数量（连续同 dest = OUTBOUND batch, 连续同 pick = INBOUND batch）
        n_batches = 0
        i = 0
        while i < len(sorted_tasks):
            j = i + 1
            # 连续同 dest → OUTBOUND batch
            while j < len(sorted_tasks) and sorted_tasks[j].dest == sorted_tasks[i].dest:
                j += 1
            if j > i + 1:
                n_batches += 1
                i = j
                continue
            # 连续同 pick → INBOUND batch
            while j < len(sorted_tasks) and sorted_tasks[j].pick == sorted_tasks[i].pick:
                j += 1
            if j > i + 1:
                n_batches += 1
                i = j
                continue
            n_batches += 1
            i += 1
        n_tasks = len(sorted_tasks)

        # turn/accel/decel 按 batch 数（batch 内连续取货是一趟）
        # load N 次 + unload N 次（物理上逐个操作）
        return (total_dist * c.AGV_MOVE_TIME
                + n_batches * c.AGV_TURN_TIME
                + (c.AGV_ACCEL_TIME + c.AGV_DECEL_TIME) * n_batches
                + n_tasks * 2 * c.AGV_LOAD_UNLOAD_TIME)

    def allocate(self, clusters: list[TaskCluster], agv_states: list[AGVState],
                 zone_pos: dict[str, tuple[int, int]]) -> tuple[dict[int, list[TaskCluster]], int]:
        if not self.config.ablation.enable_cp_sat:
            return self._greedy_allocate(clusters, agv_states, zone_pos)

        agv_num = len(agv_states)
        cluster_num = len(clusters)
        if cluster_num == 0:
            return {s.agv_id: [] for s in agv_states}, 0

        # 计算代价矩阵
        cost_matrix = []
        max_cost = 0
        for agv in agv_states:
            row = []
            for cluster in clusters:
                t = self._calc_cluster_time(cluster, agv.init_pos, zone_pos)
                row.append(t)
                if t > max_cost:
                    max_cost = t
            cost_matrix.append(row)

        upper = int(max_cost * cluster_num * 1.2) + 1

        model = cp_model.CpModel()
        x = {}
        for k in range(agv_num):
            for v in range(cluster_num):
                x[(k, v)] = model.NewBoolVar(f"a{k}_c{v}")

        makespan = model.NewIntVar(0, upper, "makespan")

        # 每个簇恰好分配给一个AGV
        for v in range(cluster_num):
            model.Add(sum(x[(k, v)] for k in range(agv_num)) == 1)

        # 容量约束
        for k in range(agv_num):
            total_tasks = sum(x[(k, v)] * clusters[v].task_num for v in range(cluster_num))
            model.Add(total_tasks <= self.config.AGV_MAX_TASK_CAPACITY * 2)

        # 紧急优先级约束
        for v in range(cluster_num):
            if clusters[v].priority == 10:  # URGENT
                min_cost = min(cost_matrix[k][v] for k in range(agv_num))
                for k in range(agv_num):
                    if cost_matrix[k][v] > min_cost * 1.2:
                        model.Add(x[(k, v)] == 0)

        # makespan约束
        for k in range(agv_num):
            agv_time = sum(x[(k, v)] * cost_matrix[k][v] for v in range(cluster_num))
            model.Add(makespan >= agv_time)

        model.Minimize(makespan)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.config.CP_SAT_TIME_LIMIT
        solver.parameters.num_search_workers = 8
        solver.parameters.random_seed = self.config.RANDOM_SEED

        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            result: dict[int, list[TaskCluster]] = defaultdict(list)
            for k in range(agv_num):
                for v in range(cluster_num):
                    if solver.Value(x[(k, v)]) == 1:
                        result[agv_states[k].agv_id].append(clusters[v])
            # 计算实际makespan
            ms = 0
            for k in range(agv_num):
                t = sum(cost_matrix[k][v]
                        for v in range(cluster_num)
                        if solver.Value(x[(k, v)]) == 1)
                ms = max(ms, t)
            return result, ms
        else:
            return self._greedy_allocate(clusters, agv_states, zone_pos)

    def _greedy_allocate(self, clusters: list[TaskCluster], agv_states: list[AGVState],
                         zone_pos: dict[str, tuple[int, int]]) -> tuple[dict[int, list[TaskCluster]], int]:
        result: dict[int, list[TaskCluster]] = defaultdict(list)
        agv_times = [0] * len(agv_states)

        sorted_clusters = sorted(clusters, key=lambda c: (-c.priority, -c.task_num))
        for cluster in sorted_clusters:
            idx = int(np.argmin(agv_times))
            result[agv_states[idx].agv_id].append(cluster)
            agv_times[idx] += self._calc_cluster_time(cluster, agv_states[idx].init_pos, zone_pos)

        return result, int(max(agv_times)) if agv_times else 0
