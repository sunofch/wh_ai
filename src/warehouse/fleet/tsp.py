# src/warehouse/fleet/tsp.py
"""OR-Tools TSP任务排序（支持双向batch：OUTBOUND多取一送 + INBOUND一取多送）"""

from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING

from ortools.constraint_solver import routing_enums_pb2, pywrapcp

if TYPE_CHECKING:
    from src.warehouse.fleet.pathfinding import PathFinder
    from src.warehouse.wms.config import WarehouseConfig
    from src.warehouse.models import TransportTask

# batch 类型标记
_OUTBOUND = "outbound"   # 多取一送: [取→取→取]→送
_INBOUND = "inbound"     # 一取多送: 取→[送→送→送]


class TSPSolver:
    def __init__(self, path_finder: PathFinder, config: WarehouseConfig):
        self.path_finder = path_finder
        self.config = config

    # ── Batch 分组 ──

    def _group_by_dest(self, tasks: list[TransportTask]) -> list[list[TransportTask]]:
        """按 dest 分组（OUTBOUND batch）"""
        groups: dict[str, list[TransportTask]] = defaultdict(list)
        for t in tasks:
            groups[t.dest].append(t)
        return list(groups.values())

    def _group_by_pick(self, tasks: list[TransportTask]) -> list[list[TransportTask]]:
        """按 pick 分组（INBOUND batch）"""
        groups: dict[str, list[TransportTask]] = defaultdict(list)
        for t in tasks:
            groups[t.pick].append(t)
        return list(groups.values())

    # ── Batch 内排序 ──

    def _sort_batch_picks(self, batch: list[TransportTask],
                          start_pos: tuple[int, int],
                          zone_pos: dict[str, tuple[int, int]]) -> list[TransportTask]:
        """OUTBOUND batch: 最近邻排 pick 点（从 start_pos 出发）"""
        if len(batch) <= 1:
            return list(batch)
        remaining = list(batch)
        sorted_batch: list[TransportTask] = []
        current = start_pos
        while remaining:
            best_idx, best_dist = 0, float('inf')
            for i, t in enumerate(remaining):
                d = self.path_finder.get_distance(current, zone_pos.get(t.pick, current))
                if d < best_dist:
                    best_dist, best_idx = d, i
            chosen = remaining.pop(best_idx)
            sorted_batch.append(chosen)
            current = zone_pos.get(chosen.pick, current)
        return sorted_batch

    def _sort_batch_dests(self, batch: list[TransportTask],
                          start_pos: tuple[int, int],
                          zone_pos: dict[str, tuple[int, int]]) -> list[TransportTask]:
        """INBOUND batch: 最近邻排 dest 点（从 pick 出发）"""
        if len(batch) <= 1:
            return list(batch)
        remaining = list(batch)
        sorted_batch: list[TransportTask] = []
        current = start_pos
        while remaining:
            best_idx, best_dist = 0, float('inf')
            for i, t in enumerate(remaining):
                d = self.path_finder.get_distance(current, zone_pos.get(t.dest, current))
                if d < best_dist:
                    best_dist, best_idx = d, i
            chosen = remaining.pop(best_idx)
            sorted_batch.append(chosen)
            current = zone_pos.get(chosen.dest, current)
        return sorted_batch

    # ── Batch 内部距离 ──

    def _outbound_batch_distance(self, sorted_batch: list[TransportTask],
                                 start_pos: tuple[int, int],
                                 zone_pos: dict[str, tuple[int, int]]) -> int:
        """OUTBOUND batch: start_pos → pick_1 → ... → pick_N → dest"""
        total = 0
        current = start_pos
        for t in sorted_batch:
            pick_pos = zone_pos.get(t.pick, current)
            total += self.path_finder.get_distance(current, pick_pos)
            current = pick_pos
        dest_pos = zone_pos.get(sorted_batch[0].dest, start_pos)
        total += self.path_finder.get_distance(current, dest_pos)
        return total

    def _inbound_batch_distance(self, sorted_batch: list[TransportTask],
                                start_pos: tuple[int, int],
                                zone_pos: dict[str, tuple[int, int]]) -> int:
        """INBOUND batch: start_pos → pick → dest_1 → ... → dest_N"""
        if not sorted_batch:
            return 0
        total = 0
        current = start_pos
        pick_pos = zone_pos.get(sorted_batch[0].pick, current)
        total += self.path_finder.get_distance(current, pick_pos)
        current = pick_pos
        for t in sorted_batch:
            dest_pos = zone_pos.get(t.dest, current)
            total += self.path_finder.get_distance(current, dest_pos)
            current = dest_pos
        return total

    # ── 距离矩阵构建 ──

    def _build_batch_distance_matrix(
        self, batches: list[list[TransportTask]],
        batch_types: list[str],
        agv_pos: tuple[int, int],
        zone_pos: dict[str, tuple[int, int]],
    ) -> list[list[int]]:
        """构建混合方向 batch 粒度距离矩阵

        OUTBOUND batch: entry=最近的pick, exit=dest
        INBOUND  batch: entry=pick, exit=最近dest的最后一个
        """
        n = len(batches) + 1
        matrix = [[0] * n for _ in range(n)]

        entries = []
        exits = []
        for batch, btype in zip(batches, batch_types):
            if btype == _OUTBOUND:
                dest_pos = zone_pos.get(batch[0].dest, agv_pos)
                best_pick = min(
                    batch,
                    key=lambda t: self.path_finder.get_distance(
                        zone_pos.get(t.pick, agv_pos), dest_pos),
                )
                entries.append(zone_pos.get(best_pick.pick, agv_pos))
                exits.append(dest_pos)
            else:  # INBOUND
                pick_pos = zone_pos.get(batch[0].pick, agv_pos)
                best_dest = min(
                    batch,
                    key=lambda t: self.path_finder.get_distance(
                        pick_pos, zone_pos.get(t.dest, agv_pos)),
                )
                entries.append(pick_pos)
                exits.append(zone_pos.get(best_dest.dest, agv_pos))

        for j in range(len(batches)):
            internal = self.path_finder.get_distance(entries[j], exits[j])
            matrix[0][j + 1] = self.path_finder.get_distance(agv_pos, entries[j]) + internal

        for i in range(len(batches)):
            for j in range(len(batches)):
                if i == j:
                    continue
                internal_j = self.path_finder.get_distance(entries[j], exits[j])
                matrix[i + 1][j + 1] = self.path_finder.get_distance(exits[i], entries[j]) + internal_j
        return matrix

    def _build_single_distance_matrix(self, tasks: list[TransportTask],
                                      agv_pos: tuple[int, int],
                                      zone_pos: dict[str, tuple[int, int]]) -> list[list[int]]:
        """单任务距离矩阵（原始取一送一模式）"""
        n = len(tasks) + 1
        matrix = [[0] * n for _ in range(n)]
        for i, task in enumerate(tasks):
            pick_pos = zone_pos.get(task.pick, agv_pos)
            dest_pos = zone_pos.get(task.dest, agv_pos)
            matrix[0][i + 1] = (self.path_finder.get_distance(agv_pos, pick_pos)
                                + self.path_finder.get_distance(pick_pos, dest_pos))
        for i in range(len(tasks)):
            dest_i = zone_pos.get(tasks[i].dest, agv_pos)
            for j in range(len(tasks)):
                if i == j:
                    continue
                pick_j = zone_pos.get(tasks[j].pick, agv_pos)
                dest_j = zone_pos.get(tasks[j].dest, agv_pos)
                matrix[i + 1][j + 1] = (self.path_finder.get_distance(dest_i, pick_j)
                                        + self.path_finder.get_distance(pick_j, dest_j))
        return matrix

    # ── OR-Tools TSP 求解 ──

    def _solve_tsp(self, dist_matrix: list[list[int]], n_nodes: int) -> list[int]:
        """底层 OR-Tools TSP 求解，返回节点索引顺序（不含 depot 0）"""
        manager = pywrapcp.RoutingIndexManager(n_nodes + 1, 1, 0)
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
                    order.append(node - 1)
                idx = solution.Value(routing.NextVar(idx))
            return order
        return list(range(n_nodes))

    # ── 距离计算 ──

    def _chain_distance(self, tasks: list[TransportTask],
                        agv_pos: tuple[int, int],
                        zone_pos: dict[str, tuple[int, int]]) -> int:
        """取一送一模式行程距离（AGV→pick1→dest1→pick2→dest2→...）"""
        total = 0
        prev = agv_pos
        for t in tasks:
            pp = zone_pos.get(t.pick, agv_pos)
            dp = zone_pos.get(t.dest, agv_pos)
            total += self.path_finder.get_distance(prev, pp)
            total += self.path_finder.get_distance(pp, dp)
            prev = dp
        return total

    # ── 主入口 ──

    def optimize(self, tasks: list[TransportTask],
                 agv_pos: tuple[int, int],
                 zone_pos: dict[str, tuple[int, int]]) -> tuple[list[TransportTask], int]:
        """返回 (排序后的任务列表, 总距离) — 支持双向 batch

        OUTBOUND/TRANSFER: 按 dest 分组 → 多取一送（[取→取→取]→送）
        INBOUND:           按 pick 分组 → 一取多送（取→[送→送→送]）
        """
        if not tasks:
            return [], 0
        if len(tasks) == 1 or not self.config.ablation.enable_tsp:
            sorted_tasks = sorted(tasks, key=lambda t: -t.priority)
            return sorted_tasks, self._chain_distance(sorted_tasks, agv_pos, zone_pos)

        from src.warehouse.models import TaskType

        # Step 1: 按方向分离任务
        ob_tasks = [t for t in tasks if t.task_type != TaskType.INBOUND]
        ib_tasks = [t for t in tasks if t.task_type == TaskType.INBOUND]

        # Step 2: 分别分组
        all_batches: list[list[TransportTask]] = []
        batch_types: list[str] = []

        for b in self._group_by_dest(ob_tasks):
            all_batches.append(b)
            batch_types.append(_OUTBOUND)

        for b in self._group_by_pick(ib_tasks):
            all_batches.append(b)
            batch_types.append(_INBOUND)

        # 无 batch 机会 → 退化原始 TSP
        if all(len(b) == 1 for b in all_batches):
            return self._optimize_no_batch(tasks, agv_pos, zone_pos)

        # Step 3: batch 间 TSP 排序
        if len(all_batches) > 1:
            batch_matrix = self._build_batch_distance_matrix(
                all_batches, batch_types, agv_pos, zone_pos)
            batch_order = self._solve_tsp(batch_matrix, len(all_batches))
        else:
            batch_order = [0]

        # Step 4: 逐 batch 精确排序 + 计算距离
        total_dist = 0
        prev_pos = agv_pos
        result_tasks: list[TransportTask] = []

        for idx in batch_order:
            batch = all_batches[idx]
            btype = batch_types[idx]

            if btype == _OUTBOUND:
                sorted_batch = self._sort_batch_picks(batch, prev_pos, zone_pos)
                batch_dist = self._outbound_batch_distance(sorted_batch, prev_pos, zone_pos)
                exit_pos = zone_pos.get(batch[0].dest, agv_pos)
            else:  # INBOUND
                sorted_batch = self._sort_batch_dests(batch, prev_pos, zone_pos)
                batch_dist = self._inbound_batch_distance(sorted_batch, prev_pos, zone_pos)
                exit_pos = zone_pos.get(sorted_batch[-1].dest, agv_pos)

            total_dist += batch_dist
            result_tasks.extend(sorted_batch)
            prev_pos = exit_pos

        return result_tasks, total_dist

    def _optimize_no_batch(self, tasks: list[TransportTask],
                           agv_pos: tuple[int, int],
                           zone_pos: dict[str, tuple[int, int]]) -> tuple[list[TransportTask], int]:
        """原始取一送一 TSP（无 batch 合并）"""
        dist_matrix = self._build_single_distance_matrix(tasks, agv_pos, zone_pos)
        order = self._solve_tsp(dist_matrix, len(tasks))
        ordered = [tasks[i] for i in order]
        return ordered, self._chain_distance(ordered, agv_pos, zone_pos)
