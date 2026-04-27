# src/warehouse/fleet/map_builder.py
"""仓库地图构建器 — 封装原11个全局变量"""

from __future__ import annotations
import numpy as np
from src.warehouse.models import MapConfig


# 地图格子类型常量
MAP_OBSTACLE = 0
MAP_PASSABLE = 1
MAP_WAREHOUSE = 2
MAP_PORT = 3
MAP_YIELD_POINT = 4
MAP_CHARGING = 5


class WarehouseMap:
    """封装仓库网格地图及所有空间数据"""

    def __init__(self, map_config: MapConfig):
        self.config = map_config
        self.grid: np.ndarray = np.zeros(
            (map_config.grid_size, map_config.grid_size), dtype=int
        )
        # 位置名→坐标 映射
        self.zone_pos: dict[str, tuple[int, int]] = {}
        # 端口信息
        self.port_info: dict[str, dict] = {}
        # 储位列表
        self.storage_list: list[str] = []
        # 仓库区名→配置
        self.warehouse_zones: dict[str, dict] = {}
        # 充电桩坐标
        self.charging_points: list[tuple[int, int]] = []
        self._build()

    def _build(self):
        cfg = self.config
        gs = cfg.grid_size

        # 1. 主通道
        for x in cfg.main_channels_x:
            self.grid[4:gs - 4, x] = MAP_PASSABLE
        for y in cfg.main_channels_y:
            self.grid[y, 4:gs - 4] = MAP_PASSABLE

        # 2. 端口
        for port_name, pcfg in cfg.ports.items():
            x1, x2, y1, y2 = pcfg["area"]
            self.grid[y1:y2, x1:x2] = MAP_PORT
            self.zone_pos[port_name] = pcfg["pos"]
            self.port_info[port_name] = pcfg

        # 3. 仓库区 + 储位
        for wh_name, wcfg in cfg.warehouse_zones.items():
            sx, sy = wcfg["pos"]
            w, h = wcfg["w"], wcfg["h"]
            self.grid[sy:sy + h, sx:sx + w] = MAP_WAREHOUSE
            # 内部通道
            self.grid[sy + 2, sx:sx + w] = MAP_PASSABLE
            self.grid[sy:sy + h, sx + 3] = MAP_PASSABLE
            self.zone_pos[wh_name] = (sx + 3, sy + 2)
            self.warehouse_zones[wh_name] = wcfg

            # 4个储位
            storage_coords = [
                (sx + 1, sy + 1), (sx + 5, sy + 1),
                (sx + 1, sy + 3), (sx + 5, sy + 3),
            ]
            for i, (dx, dy) in enumerate(storage_coords):
                sname = f"{wh_name}_S{i + 1}"
                self.zone_pos[sname] = (dx, dy)
                self.storage_list.append(sname)
                self.grid[dy, dx] = MAP_WAREHOUSE

        # 4. 避让点
        for yp_id, pos in cfg.yield_points.items():
            x, y = pos
            self.grid[y, x] = MAP_YIELD_POINT
            self.zone_pos[yp_id] = pos

        # 5. 充电桩
        for pos in cfg.charging_points:
            x, y = pos
            self.grid[y, x] = MAP_CHARGING
            self.zone_pos[f"Charge_{pos}"] = pos
            self.charging_points.append(pos)

    def is_passable(self, x: int, y: int) -> bool:
        gs = self.config.grid_size
        if not (0 <= x < gs and 0 <= y < gs):
            return False
        return self.grid[y, x] in (MAP_PASSABLE, MAP_WAREHOUSE, MAP_PORT,
                                    MAP_YIELD_POINT, MAP_CHARGING)

    def get_distance_matrix(self) -> dict[str, int]:
        """返回 zone_pos 中所有点对的曼哈顿距离矩阵（key: "name1_name2"）"""
        dist = {}
        names = list(self.zone_pos.keys())
        for i, n1 in enumerate(names):
            for n2 in names[i + 1:]:
                p1, p2 = self.zone_pos[n1], self.zone_pos[n2]
                d = abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])
                dist[f"{n1}_{n2}"] = d
                dist[f"{n2}_{n1}"] = d
        return dist
