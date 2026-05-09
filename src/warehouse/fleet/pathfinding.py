# src/warehouse/fleet/pathfinding.py
"""时空A*路径规划 + 缓存

两层路径规划:
  - find_base_path: 基础A*(无时空约束), 用于TSP距离计算, 带路径缓存
  - find_path: 时空A*(含冲突检测), 用于仿真执行, 考虑转弯/加速代价

时空占用表(SpaceTimeTable)追踪每个(x,y,t)的AGV占用, 避免碰撞。
"""

from __future__ import annotations
import heapq
from typing import TYPE_CHECKING

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
    """时空占用表: 追踪每个(x, y, t)格子的AGV占用情况"""

    def __init__(self, grid_size: int, max_step: int = 15000):
        self.grid_size = grid_size
        self.max_step = max_step
        self.occupation: dict[tuple, int] = {}
        self.path_calc_count: int = 0

    def check_occupation(self, x: int, y: int, t_start: int, t_end: int, agv_id: int) -> tuple[bool, int | None]:
        for t in range(t_start, t_end + 1):
            key = (x, y, t)
            if key in self.occupation and self.occupation[key] != agv_id:
                return False, self.occupation[key]
        return True, None

    def lock_occupation(self, x: int, y: int, t_start: int, t_end: int, agv_id: int) -> None:
        for t in range(t_start, t_end + 1):
            key = (x, y, t)
            if key not in self.occupation or self.occupation[key] == agv_id:
                self.occupation[key] = agv_id


class PathFinder:
    """时空A*路径规划器

    提供两种模式:
      - find_base_path: 无时空约束的纯A*, 缓存结果用于TSP距离估算
      - find_path: 带时空占用的A*, 用于仿真中的实际路径规划
    """

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

    def _is_passable(self, cur: tuple[int, int], nxt: tuple[int, int]) -> bool:
        gw = self.wmap.config.grid_size
        gh = self.wmap.config.grid_height or gw
        nx, ny = nxt
        if not (0 <= nx < gw and 0 <= ny < gh):
            return False
        cell = self.grid[ny][nx]
        return cell != 0  # MAP_OBSTACLE

    def find_base_path(self, start: tuple, end: tuple) -> tuple[list[tuple[int, int]], int]:
        """基础A*（无时空约束，方向感知），带缓存

        用于TSP距离计算。状态空间为(x, y, direction), 避免路径出现不合理转弯。
        返回 (路径坐标列表, 路径长度)。
        """
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
                dist = len(path) - 1 if len(path) > 1 else 0
                self._cache_path(cache_key, path, dist)
                return path, dist

            for dx, dy, _, move_dir_str in DIRECTIONS:
                nx, ny = x + dx, y + dy
                nxt = (nx, ny)
                if not self._is_passable((x, y), nxt):
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
                  init_dir, current_step: int, agv_id: int):
        """时空A*（带冲突检测），返回 (path, turns, total_time, path_times)

        每步代价 = AGV_MOVE_TIME + (转弯 ? AGV_TURN_TIME : 0) + (起步 ? AGV_ACCEL_TIME : 0)
        冲突时AGV原地等待1步再重新搜索。搜索上限 A_MAX_SEARCH 步。
        返回非均匀时间步的路径: path_times[i] 表示到达 path[i] 的时刻。
        """
        start = (int(start[0]), int(start[1]))
        end = (int(end[0]), int(end[1]))
        if start == end:
            return [start], 0, 0, [current_step]

        if isinstance(init_dir, str):
            init_dir_str = init_dir
        else:
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
                path_times = []
                cur = state_key
                while cur in came_from:
                    path.append((cur[0], cur[1]))
                    path_times.append(cur[3])
                    cur = came_from[cur]
                path.append(start)
                path_times.append(current_step)
                path.reverse()
                path_times.reverse()
                turns = 0
                for j in range(2, len(path)):
                    dx0 = path[j-1][0] - path[j-2][0]
                    dy0 = path[j-1][1] - path[j-2][1]
                    dx1 = path[j][0] - path[j-1][0]
                    dy1 = path[j][1] - path[j-1][1]
                    if (dx0, dy0) != (dx1, dy1):
                        turns += 1
                total_time = path_times[-1] - current_step
                return path, turns, total_time, path_times

            can_move = False
            for dx, dy, _, move_dir_str in DIRECTIONS:
                nx, ny = x + dx, y + dy
                nxt = (nx, ny)

                if not self._is_passable((x, y), nxt):
                    continue

                turn_cost = c.AGV_TURN_TIME if move_dir_str != cur_dir else 0
                accel_cost = c.AGV_ACCEL_TIME if cur_t == current_step else 0
                step_cost = c.AGV_MOVE_TIME + turn_cost + accel_cost
                next_t = cur_t + step_cost

                # 检查下一位置在到达时刻是否空闲
                is_free, _ = self.st_table.check_occupation(nx, ny, next_t, next_t, agv_id)
                if not is_free:
                    continue
                # 检查转弯期间当前位置是否空闲
                if turn_cost > 0:
                    is_free_stay, _ = self.st_table.check_occupation(x, y, cur_t + 1, cur_t + turn_cost, agv_id)
                    if not is_free_stay:
                        continue

                can_move = True
                new_g = cur_g + step_cost
                new_state = (nx, ny, move_dir_str, next_t)
                if new_state not in g_score or new_g < g_score[new_state]:
                    came_from[new_state] = state_key
                    g_score[new_state] = new_g
                    heapq.heappush(open_heap, (new_g + self._heuristic(nxt, end), nx, ny, move_dir_str, next_t, new_g))

            # 所有方向被占时原地等待 1 步
            if not can_move:
                wait_t = cur_t + c.AGV_MOVE_TIME
                wait_state = (x, y, cur_dir, wait_t)
                if wait_state not in closed:
                    wait_g = cur_g + c.AGV_MOVE_TIME
                    if wait_state not in g_score or wait_g < g_score[wait_state]:
                        came_from[wait_state] = state_key
                        g_score[wait_state] = wait_g
                        heapq.heappush(open_heap, (wait_g + self._heuristic((x, y), end), x, y, cur_dir, wait_t, wait_g))

        # fallback — 从路径计算时间
        path, _ = self.find_base_path(start, end)
        dir_prev = init_dir_str
        turns = 0
        path_times = [current_step]
        for i in range(1, len(path)):
            dx = path[i][0] - path[i - 1][0]
            dy = path[i][1] - path[i - 1][1]
            d = "RIGHT" if dx > 0 else "LEFT" if dx < 0 else "DOWN" if dy > 0 else "UP"
            tc = c.AGV_TURN_TIME if d != dir_prev else 0
            ac = c.AGV_ACCEL_TIME if i == 1 else 0
            path_times.append(path_times[-1] + c.AGV_MOVE_TIME + tc + ac)
            if d != dir_prev:
                turns += 1
            dir_prev = d
        total_time = path_times[-1] - current_step
        return path, turns, total_time, path_times

    def precompute_all_paths(self) -> None:
        """预计算所有关键点之间的路径(每个区域首个储位 + 端口 + AGV初始位置)"""
        if not self.config.ablation.enable_path_cache:
            return
        key_points = []
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
        """获取两点间的A*最短距离(步数), 优先查缓存"""
        start = (int(start[0]), int(start[1]))
        end = (int(end[0]), int(end[1]))
        cache_key = f"{start[0]}_{start[1]}_{end[0]}_{end[1]}"
        if cache_key in self._dist_cache:
            return self._dist_cache[cache_key]
        _, dist = self.find_base_path(start, end)
        return dist

    def lock_path(self, path: list[tuple[int, int]], path_times: list[int],
                  agv_id: int) -> None:
        """锁定路径的时空占用: 每个位置从到达时刻到下一位置到达前一刻"""
        for i, (x, y) in enumerate(path):
            t_start = path_times[i]
            # 占用到下一位置到达前一刻（含转弯/加速停留）
            t_end = path_times[i + 1] - 1 if i + 1 < len(path_times) else t_start
            t_end = min(t_end, self.st_table.max_step - 1)
            if t_start <= t_end:
                self.st_table.lock_occupation(x, y, t_start, t_end, agv_id)

    def lock_wait(self, pos: tuple[int, int], start_t: int, duration: int, agv_id: int) -> None:
        """锁定等待期间的时空占用(装卸/充电时AGV停留在原位)"""
        x, y = pos
        end_t = min(start_t + duration - 1, self.st_table.max_step - 1)
        if start_t <= end_t:
            self.st_table.lock_occupation(x, y, start_t, end_t, agv_id)
