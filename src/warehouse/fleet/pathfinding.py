# src/warehouse/fleet/pathfinding.py
"""时空A*路径规划 + 缓存"""

from __future__ import annotations
import heapq
from collections import defaultdict
from typing import TYPE_CHECKING

import numpy as np

from src.warehouse.fleet.map_builder import (
    MAP_PASSABLE, MAP_STORAGE, MAP_PORT, MAP_YIELD_POINT, MAP_CHARGING,
    MAP_AISLE_DOWN, MAP_AISLE_UP, MAP_SUB_AISLE,
)

if TYPE_CHECKING:
    from src.warehouse.fleet.map_builder import WarehouseMap
    from src.warehouse.wms.config import WarehouseConfig


# 方向常量
DIR_X = 0
DIR_Y = 1
DIRECTIONS = [
    (-1, 0, DIR_X, "LEFT"),
    (1, 0, DIR_X, "RIGHT"),
    (0, -1, DIR_Y, "UP"),
    (0, 1, DIR_Y, "DOWN"),
]


class SpaceTimeTable:
    """时空占用表"""

    def __init__(self, grid_size: int, max_step: int = 15000):
        self.grid_size = grid_size
        self.max_step = max_step
        self.occupation: dict[tuple, int] = {}
        self.segment_occupation: dict[tuple, tuple[int, str]] = {}
        self.yield_point_occupation: dict[tuple, int] = {}
        self.path_calc_count: int = 0

    def check_occupation(self, x: int, y: int, t_start: int, t_end: int, agv_id: int) -> tuple[bool, int | None]:
        for t in range(t_start, t_end + 1):
            key = (x, y, t)
            if key in self.occupation and self.occupation[key] != agv_id:
                return False, self.occupation[key]
        return True, None

    def lock_occupation(self, x: int, y: int, t_start: int, t_end: int, agv_id: int) -> None:
        for t in range(t_start, t_end + 1):
            self.occupation[(x, y, t)] = agv_id

    def check_segment(self, seg_id: str, direction: str, t_start: int, t_end: int, agv_id: int) -> tuple[bool, int | None]:
        for t in range(t_start, t_end + 1):
            key = (seg_id, t)
            if key in self.segment_occupation:
                occ_agv, occ_dir = self.segment_occupation[key]
                if occ_agv != agv_id and occ_dir != direction:
                    return False, occ_agv
        return True, None

    def lock_segment(self, seg_id: str, direction: str, t_start: int, t_end: int, agv_id: int) -> None:
        for t in range(t_start, t_end + 1):
            self.segment_occupation[(seg_id, t)] = (agv_id, direction)

    def check_yield_point(self, yp_id: str, t_start: int, t_end: int, agv_id: int) -> tuple[bool, int | None]:
        for t in range(t_start, t_end + 1):
            key = (yp_id, t)
            if key in self.yield_point_occupation and self.yield_point_occupation[key] != agv_id:
                return False, self.yield_point_occupation[key]
        return True, None

    def lock_yield_point(self, yp_id: str, t_start: int, t_end: int, agv_id: int) -> None:
        for t in range(t_start, t_end + 1):
            self.yield_point_occupation[(yp_id, t)] = agv_id


class PathFinder:
    """时空A*路径规划器"""

    def __init__(self, warehouse_map: WarehouseMap, config: WarehouseConfig):
        self.wmap = warehouse_map
        self.config = config
        self.grid = warehouse_map.grid
        self.st_table = SpaceTimeTable(warehouse_map.config.grid_size)
        self._path_cache: dict[str, list[tuple[int, int]]] = {}
        self._dist_cache: dict[str, int] = {}
        self._cache_enabled = config.ablation.enable_path_cache

    def _cache_path(self, key: str, path: list[tuple[int, int]], dist: int) -> None:
        if self._cache_enabled:
            self._path_cache[key] = path
            self._dist_cache[key] = dist

    @staticmethod
    def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _is_passable(self, cur: tuple[int, int], nxt: tuple[int, int], cur_dir_str: str, move_dir_str: str) -> bool:
        gs = self.wmap.config.grid_size
        nx, ny = nxt
        if not (0 <= nx < gs and 0 <= ny < gs):
            return False
        cell = self.grid[ny][nx]
        if cell == 0:  # MAP_OBSTACLE
            return False
        if cell == MAP_AISLE_DOWN:
            dx, dy = nx - cur[0], ny - cur[1]
            if dy < 0:
                return False
        if cell == MAP_AISLE_UP:
            dx, dy = nx - cur[0], ny - cur[1]
            if dy > 0:
                return False
        return True

    def _is_in_conflict_segment(self, pos: tuple[int, int]) -> tuple[str | None, str | None]:
        for seg_id, seg_info in self.wmap.config.conflict_segments.items():
            start, end = seg_info["start"], seg_info["end"]
            if start[1] == end[1] == pos[1] and min(start[0], end[0]) <= pos[0] <= max(start[0], end[0]):
                return seg_id, seg_info["direction"]
            if start[0] == end[0] == pos[0] and min(start[1], end[1]) <= pos[1] <= max(start[1], end[1]):
                return seg_id, seg_info["direction"]
        return None, None

    def find_base_path(self, start: tuple, end: tuple) -> tuple[list[tuple[int, int]], int]:
        """基础A*（无时空约束），带缓存"""
        self.st_table.path_calc_count += 1
        start = (int(start[0]), int(start[1]))
        end = (int(end[0]), int(end[1]))
        cache_key = f"{start[0]}_{start[1]}_{end[0]}_{end[1]}"

        if self.config.ablation.enable_path_cache and cache_key in self._path_cache:
            return self._path_cache[cache_key], self._dist_cache[cache_key]

        if start == end:
            self._cache_path(cache_key, [start], 0)
            return [start], 0

        open_heap: list[tuple] = []
        heapq.heappush(open_heap, (self._heuristic(start, end), start[0], start[1], 0, "RIGHT"))
        came_from: dict[tuple, tuple] = {}
        g_score: dict[tuple, int] = {(start[0], start[1], "RIGHT"): 0}
        closed: set[tuple] = set()

        while open_heap:
            f, x, y, cur_g, cur_dir = heapq.heappop(open_heap)
            state_key = (x, y, cur_dir)
            if state_key in closed:
                continue
            closed.add(state_key)

            if (x, y) == end:
                path = []
                cur = state_key
                while cur in came_from:
                    path.append((cur[0], cur[1]))
                    cur = came_from[cur]
                path.append(start)
                path.reverse()
                dist = len(path)
                self._cache_path(cache_key, path, dist)
                return path, dist

            for dx, dy, _, move_dir_str in DIRECTIONS:
                nx, ny = x + dx, y + dy
                nxt = (nx, ny)
                if not self._is_passable((x, y), nxt, cur_dir, move_dir_str):
                    continue
                new_g = cur_g + 1
                ns = (nx, ny, move_dir_str)
                if ns not in g_score or new_g < g_score[ns]:
                    came_from[ns] = state_key
                    g_score[ns] = new_g
                    heapq.heappush(open_heap, (new_g + self._heuristic(nxt, end), nx, ny, new_g, move_dir_str))

        # fallback
        path = [start, end]
        dist = self._heuristic(start, end)
        self._cache_path(cache_key, path, dist)
        return path, dist

    def find_path(self, start: tuple, end: tuple, load_state: int,
                  init_dir: int, current_step: int, agv_id: int) -> tuple[list[tuple[int, int]], int, int]:
        """时空A*（带冲突检测）"""
        start = (int(start[0]), int(start[1]))
        end = (int(end[0]), int(end[1]))
        if start == end:
            return [start], 0, 0

        init_dir_str = "RIGHT" if init_dir == DIR_X else "DOWN"
        c = self.config

        open_heap: list[tuple] = []
        heapq.heappush(open_heap, (self._heuristic(start, end), start[0], start[1], init_dir_str, current_step, 0))
        came_from: dict[tuple, tuple] = {}
        g_score: dict[tuple, int] = {(start[0], start[1], init_dir_str, current_step): 0}
        closed: set[tuple] = set()
        search_count = 0

        while open_heap and search_count < c.A_MAX_SEARCH:
            search_count += 1
            f, x, y, cur_dir, cur_t, cur_g = heapq.heappop(open_heap)
            state_key = (x, y, cur_dir, cur_t)
            if state_key in closed:
                continue
            closed.add(state_key)

            if (x, y) == end:
                path = []
                cur = state_key
                while cur in came_from:
                    path.append((cur[0], cur[1]))
                    cur = came_from[cur]
                path.append(start)
                path.reverse()
                # 计算转弯次数和时间
                dir_list = [init_dir_str]
                for i in range(1, len(path)):
                    dx = path[i][0] - path[i - 1][0]
                    dir_list.append("RIGHT" if dx > 0 else "LEFT" if dx < 0 else dir_list[-1])
                turns = sum(1 for i in range(1, len(dir_list)) if dir_list[i] != dir_list[i - 1])
                base_time = len(path) * c.AGV_MOVE_TIME
                accel_time = (c.AGV_ACCEL_TIME + c.AGV_DECEL_TIME) if len(path) > 1 else 0
                turn_time = turns * c.AGV_TURN_TIME
                return path, turns, base_time + accel_time + turn_time

            for dx, dy, _, move_dir_str in DIRECTIONS:
                nx, ny = x + dx, y + dy
                nxt = (nx, ny)
                next_t = cur_t + c.AGV_MOVE_TIME

                if not self._is_passable((x, y), nxt, cur_dir, move_dir_str):
                    continue

                # 冲突路段检测
                if self.config.ablation.enable_conflict_avoid:
                    seg_id, seg_dir = self._is_in_conflict_segment(nxt)
                    if seg_id:
                        seg_free, _ = self.st_table.check_segment(seg_id, seg_dir, cur_t + 1, next_t, agv_id)
                        if not seg_free:
                            yp_id = self.wmap.config.conflict_segments[seg_id]["yield_points"][0]
                            yp_free, _ = self.st_table.check_yield_point(yp_id, cur_t + 1, cur_t + 15, agv_id)
                            if yp_free:
                                self.st_table.lock_yield_point(yp_id, cur_t + 1, cur_t + 15, agv_id)
                                yp_pos = self.wmap.config.yield_points[yp_id]
                                nxt = yp_pos
                                next_t = cur_t + 15
                            else:
                                continue

                # 时空占用检查
                is_free, _ = self.st_table.check_occupation(nx, ny, cur_t + 1, next_t, agv_id)
                if not is_free:
                    continue

                turn_cost = c.AGV_TURN_TIME if move_dir_str != cur_dir else 0
                accel_cost = c.AGV_ACCEL_TIME if cur_t == current_step else 0
                new_g = cur_g + c.AGV_MOVE_TIME + turn_cost + accel_cost
                new_state = (nx, ny, move_dir_str, next_t)
                if new_state not in g_score or new_g < g_score[new_state]:
                    came_from[new_state] = state_key
                    g_score[new_state] = new_g
                    heapq.heappush(open_heap, (new_g + self._heuristic(nxt, end), nx, ny, move_dir_str, next_t, new_g))

        # fallback
        path, _ = self.find_base_path(start, end)
        turns = 2 if (start[0] != end[0] and start[1] != end[1]) else 0
        total_time = len(path) * c.AGV_MOVE_TIME + turns * c.AGV_TURN_TIME
        return path, turns, total_time

    def precompute_all_paths(self) -> None:
        """预计算所有关键点之间的路径"""
        if not self.config.ablation.enable_path_cache:
            return
        key_points = []
        # Use first storage of each zone as representative key point
        for zone in self.wmap.rack_zone_names:
            first = f"{zone}_R1_B1"
            if first in self.wmap.zone_pos:
                key_points.append(self.wmap.zone_pos[first])
        key_points.extend([pcfg["pos"] for pcfg in self.wmap.port_info.values()])
        key_points.extend(self.wmap.config.agv_init_positions)
        for i, start in enumerate(key_points):
            for j, end in enumerate(key_points):
                if i != j:
                    self.find_base_path(start, end)

    def get_distance(self, start: tuple, end: tuple) -> int:
        start = (int(start[0]), int(start[1]))
        end = (int(end[0]), int(end[1]))
        cache_key = f"{start[0]}_{start[1]}_{end[0]}_{end[1]}"
        if cache_key in self._dist_cache:
            return self._dist_cache[cache_key]
        _, dist = self.find_base_path(start, end)
        return dist
