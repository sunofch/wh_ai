# src/warehouse/fleet/allocator.py
"""位置感知任务分配 (makespan-aware regret + distance tie-breaker)

核心思路:
  1. Makespan 目标: 主键最小化 max(完成时间), 次键最小化新分配 AGV 的完成时间
  2. Regret-based insertion: 同优先级内, 优先分配"最优 AGV vs 次优 AGV"差距最大的簇
  3. Tie-breaker: 评分相等时按 AGV 当前位置→簇质心曼哈顿距离破局, 避免系统性偏向小 agv_id

保留簇级优先级分组(高优先级先于低优先级处理), 在组内用 regret 与 makespan 共同决策。
"""

from __future__ import annotations
from collections import defaultdict
from itertools import groupby
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
        self._time_cache: dict = {}
        self._centroid_cache: dict = {}

    def _calc_cluster_time(self, cluster: TaskCluster, agv_pos: tuple[int, int],
                           zone_pos: dict[str, tuple[int, int]]) -> tuple[int, tuple[int, int]]:
        """用 TSP 排序后精确计算簇执行代价(带缓存)

        代价 = 移动距离 × move_time + 装卸次数 × load_time + 转弯 + 加速段
        返回 (总代价, 簇出口位置)
        """
        key = (id(cluster), agv_pos)
        if key in self._time_cache:
            return self._time_cache[key]

        sorted_tasks, total_dist = self.tsp.optimize(cluster.tasks, agv_pos, zone_pos)
        c = self.config
        n_tasks = len(sorted_tasks)

        move_time = total_dist * c.AGV_MOVE_TIME
        load_time = n_tasks * 2 * c.AGV_LOAD_UNLOAD_TIME

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
        total = move_time + load_time + turns * c.AGV_TURN_TIME + segments * c.AGV_ACCEL_TIME
        self._time_cache[key] = (total, exit_pos)
        return total, exit_pos

    def _cluster_centroid(self, cluster: TaskCluster,
                          zone_pos: dict[str, tuple[int, int]]) -> tuple[float, float]:
        """簇所有 pick/dest 位置的质心(用于位置感知 tie-breaker)"""
        cid = id(cluster)
        if cid in self._centroid_cache:
            return self._centroid_cache[cid]
        positions = []
        for t in cluster.tasks:
            if t.pick in zone_pos:
                positions.append(zone_pos[t.pick])
            if t.dest in zone_pos:
                positions.append(zone_pos[t.dest])
        if not positions:
            res = (0.0, 0.0)
        else:
            cx = sum(p[0] for p in positions) / len(positions)
            cy = sum(p[1] for p in positions) / len(positions)
            res = (cx, cy)
        self._centroid_cache[cid] = res
        return res

    def allocate(self, clusters: list[TaskCluster], agv_states: list[AGVState],
                 zone_pos: dict[str, tuple[int, int]]) -> dict[int, list[TaskCluster]]:
        """分配入口: 返回 {agv_id: [assigned_clusters]}"""
        self._time_cache.clear()
        self._centroid_cache.clear()
        return self._regret_allocate(clusters, agv_states, zone_pos)

    def _regret_allocate(self, clusters: list[TaskCluster], agv_states: list[AGVState],
                         zone_pos: dict[str, tuple[int, int]]) -> dict[int, list[TaskCluster]]:
        """按优先级分组的 regret-2 贪心分配

        流程:
          - 按 priority 降序分组(高优先级组先处理完才进入下一组)
          - 组内每轮: 对所有未分配簇, 计算其在各 AGV 上的评分 (makespan, completion, dist)
                      regret = 次优 makespan - 最优 makespan + 0.001 × completion 差
                      选 regret 最大的簇 → 分给其最优 AGV
          - 同 regret 时, 选"分配后 makespan 增长更小"的簇
        """
        result: dict[int, list[TaskCluster]] = defaultdict(list)
        agv_positions = {s.agv_id: s.init_pos for s in agv_states}
        agv_times: dict[int, int] = {s.agv_id: 0 for s in agv_states}
        current_makespan = 0

        sorted_by_prio = sorted(clusters, key=lambda c: -c.priority)
        for _, group_iter in groupby(sorted_by_prio, key=lambda c: c.priority):
            unassigned = list(group_iter)

            while unassigned:
                best_pick_idx = -1
                best_regret = -1.0
                best_choice: tuple[int, int, tuple[int, int], int] | None = None
                # best_choice = (agv_id, cluster_time, exit_pos, new_makespan)

                for u_idx, cluster in enumerate(unassigned):
                    centroid = self._cluster_centroid(cluster, zone_pos)
                    options = []
                    for agv in agv_states:
                        ct, exit_pos = self._calc_cluster_time(
                            cluster, agv_positions[agv.agv_id], zone_pos
                        )
                        new_completion = agv_times[agv.agv_id] + ct
                        new_makespan = max(new_completion, current_makespan)
                        ax, ay = agv_positions[agv.agv_id]
                        dist_tie = abs(ax - centroid[0]) + abs(ay - centroid[1])
                        # 评分键: 主 makespan, 次 completion, 末 distance (tie-breaker #3)
                        options.append((new_makespan, new_completion, dist_tie,
                                        agv.agv_id, ct, exit_pos))

                    options.sort()
                    s1 = options[0]
                    s2 = options[1] if len(options) > 1 else s1
                    # Regret 主体 makespan 差; 同 makespan 时用 completion 差做微调
                    regret = (s2[0] - s1[0]) + 0.001 * max(0, s2[1] - s1[1])

                    if (regret > best_regret or
                        (regret == best_regret and best_choice is not None
                         and s1[0] < best_choice[3])):
                        best_regret = regret
                        best_pick_idx = u_idx
                        best_choice = (s1[3], s1[4], s1[5], s1[0])

                assert best_choice is not None
                agv_id, ct, exit_pos, _ = best_choice
                result[agv_id].append(unassigned[best_pick_idx])
                agv_times[agv_id] += ct
                agv_positions[agv_id] = exit_pos
                current_makespan = max(current_makespan, agv_times[agv_id])
                unassigned.pop(best_pick_idx)

        return result
