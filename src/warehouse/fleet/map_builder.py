# src/warehouse/fleet/map_builder.py
"""仓库地图构建器 — 全双向通道"""

from __future__ import annotations
import numpy as np
from src.warehouse.models import MapConfig, RackZoneConfig


# 地图格子类型常量
MAP_OBSTACLE = 0
MAP_PASSABLE = 1
MAP_STORAGE = 2
MAP_PORT = 3
MAP_CHARGING = 5


class WarehouseMap:
    """封装仓库网格地图及所有空间数据"""

    def __init__(self, map_config: MapConfig):
        self.config = map_config
        self.grid: np.ndarray = np.zeros(
            (map_config.grid_size, map_config.grid_size), dtype=int
        )
        self.zone_pos: dict[str, tuple[int, int]] = {}
        self.port_info: dict[str, dict] = {}
        self.storage_list: list[str] = []
        self.rack_zone_names: list[str] = []
        self.charging_points: list[tuple[int, int]] = []
        self._build()

    def _build(self):
        cfg = self.config
        gs = cfg.grid_size

        # 1. 初始化全通道
        self.grid[1:gs - 1, 1:gs - 1] = MAP_PASSABLE

        # 2. 端口
        for port_name, pcfg in cfg.ports.items():
            x1, x2, y1, y2 = pcfg["area"]
            self.grid[y1:y2, x1:x2] = MAP_PORT
            self.zone_pos[port_name] = pcfg["pos"]
            self.port_info[port_name] = pcfg

        # 3. 充电桩
        for pos in cfg.charging_points:
            x, y = pos
            if 0 <= x < gs and 0 <= y < gs:
                self.grid[y, x] = MAP_CHARGING
                self.zone_pos[f"Charge_{pos}"] = pos
                self.charging_points.append(pos)

        # 4. 货架区域
        for zone_name, zone_cfg in cfg.rack_zones.items():
            self._build_rack_zone(zone_name, zone_cfg)
            self.rack_zone_names.append(zone_name)

    def _build_rack_zone(self, zone_name: str, zcfg: RackZoneConfig):
        sx, sy = zcfg.pos
        gs = self.config.grid_size

        # 货架行布局：每行3个储位 + 1格巷道，重复 num_bays 次
        # ASCII: SSS.SSS.SSS.SSS → 3个S + 1个. = 4格一组，共4组 = 16格
        group_width = 4   # 3个储位 + 1格巷道
        num_groups = 4    # SSS.SSS.SSS.SSS = 4组

        # 货架行布局：每2行一组（1行储位 + 1行横向通道）
        row_pairs = min(zcfg.height // 2, 5)  # 最多5行储位

        for row_idx in range(row_pairs):
            rack_y = sy + row_idx * 2

            for g in range(num_groups):
                for s in range(3):
                    bay_x = sx + g * group_width + s
                    if bay_x >= gs or rack_y >= gs:
                        continue
                    sname = f"{zone_name}_R{row_idx + 1}_B{g * 3 + s + 1}"
                    self.zone_pos[sname] = (bay_x, rack_y)
                    self.storage_list.append(sname)
                    self.grid[rack_y, bay_x] = MAP_STORAGE

    def is_passable(self, x: int, y: int) -> bool:
        gs = self.config.grid_size
        if not (0 <= x < gs and 0 <= y < gs):
            return False
        cell = self.grid[y, x]
        return cell != MAP_OBSTACLE

    def get_distance_matrix(self) -> dict[str, int]:
        """返回 zone_pos 中所有点对的曼哈顿距离矩阵"""
        dist = {}
        names = list(self.zone_pos.keys())
        for i, n1 in enumerate(names):
            for n2 in names[i + 1:]:
                p1, p2 = self.zone_pos[n1], self.zone_pos[n2]
                d = abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])
                dist[f"{n1}_{n2}"] = d
                dist[f"{n2}_{n1}"] = d
        return dist
