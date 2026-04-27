# src/warehouse/fleet/tsp.py
"""OR-Tools TSP任务排序"""

from __future__ import annotations
from typing import TYPE_CHECKING

from ortools.constraint_solver import routing_enums_pb2, pywrapcp

if TYPE_CHECKING:
    from src.warehouse.fleet.pathfinding import PathFinder
    from src.warehouse.wms.config import WarehouseConfig
    from src.warehouse.models import TransportTask


class TSPSolver:
    def __init__(self, path_finder: PathFinder, config: WarehouseConfig):
        self.path_finder = path_finder
        self.config = config

    def _build_distance_matrix(self, tasks: list[TransportTask],
                               agv_pos: tuple[int, int],
                               zone_pos: dict[str, tuple[int, int]]) -> list[list[int]]:
        n = len(tasks) + 1  # depot + tasks
        matrix = [[0] * n for _ in range(n)]
        for i, task in enumerate(tasks):
            task_pos = zone_pos.get(task.dest, agv_pos)
            dist = self.path_finder.get_distance(agv_pos, task_pos)
            matrix[0][i + 1] = dist
            matrix[i + 1][0] = dist
        for i in range(len(tasks)):
            pos_i = zone_pos.get(tasks[i].dest, agv_pos)
            for j in range(len(tasks)):
                if i == j:
                    continue
                pos_j = zone_pos.get(tasks[j].dest, agv_pos)
                matrix[i + 1][j + 1] = self.path_finder.get_distance(pos_i, pos_j)
        return matrix

    def optimize(self, tasks: list[TransportTask],
                 agv_pos: tuple[int, int],
                 zone_pos: dict[str, tuple[int, int]]) -> tuple[list[TransportTask], int]:
        """返回 (排序后的任务列表, 总距离)"""
        if len(tasks) <= 1 or not self.config.ablation.enable_tsp:
            sorted_tasks = sorted(tasks, key=lambda t: -t.priority)
            total = sum(self.path_finder.get_distance(agv_pos, zone_pos.get(t.dest, agv_pos))
                        for t in sorted_tasks)
            return sorted_tasks, total

        dist_matrix = self._build_distance_matrix(tasks, agv_pos, zone_pos)
        manager = pywrapcp.RoutingIndexManager(len(tasks) + 1, 1, 0)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_idx, to_idx):
            return dist_matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]

        transit_cb = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GREEDY_DESCENT
        params.time_limit.seconds = self.config.TSP_TIME_LIMIT

        try:
            params.random_seed = self.config.RANDOM_SEED
        except AttributeError:
            try:
                params.solver_random_seed = self.config.RANDOM_SEED
            except AttributeError:
                pass

        solution = routing.SolveWithParameters(params)
        if solution:
            order = []
            idx = routing.Start(0)
            while not routing.IsEnd(idx):
                node = manager.IndexToNode(idx)
                if node != 0:
                    order.append(tasks[node - 1])
                idx = solution.Value(routing.NextVar(idx))
            return order, solution.ObjectiveValue()
        else:
            sorted_tasks = sorted(tasks, key=lambda t: -t.priority)
            total = sum(dist_matrix[0][i + 1] for i in range(len(tasks)))
            return sorted_tasks, total
