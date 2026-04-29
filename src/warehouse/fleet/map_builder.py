# src/warehouse/fleet/map_builder.py
"""仓库地图构建器 — 行列式货架仓，方向感知巷道"""

from __future__ import annotations
import numpy as np
from src.warehouse.models import MapConfig, RackZoneConfig, AisleConfig


# 地图格子类型常量
MAP_OBSTACLE = 0
MAP_PASSABLE = 1
MAP_STORAGE = 2
MAP_PORT = 3
MAP_YIELD_POINT = 4
MAP_CHARGING = 5
MAP_AISLE_DOWN = 6
MAP_AISLE_UP = 7
MAP_SUB_AISLE = 8


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
        self.aisle_info: dict[str, AisleConfig] = {}
        self.charging_points: list[tuple[int, int]] = []
        self._build()

    def _build(self):
        cfg = self.config
        gs = cfg.grid_size

        # 1. 主通道
        aw = cfg.main_aisle_width
        for x in cfg.main_channels_x:
            for dx in range(aw):
                col = x + dx
                if 0 <= col < gs:
                    self.grid[1:gs - 1, col] = MAP_PASSABLE
        for y in cfg.main_channels_y:
            for dy in range(aw):
                row = y + dy
                if 0 <= row < gs:
                    self.grid[row, 1:gs - 1] = MAP_PASSABLE

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

        # 4. 避让点
        for yp_id, pos in cfg.yield_points.items():
            x, y = pos
            if 0 <= x < gs and 0 <= y < gs:
                self.grid[y, x] = MAP_YIELD_POINT
                self.zone_pos[yp_id] = pos

        # 5. 货架区域
        for zone_name, zone_cfg in cfg.rack_zones.items():
            self._build_rack_zone(zone_name, zone_cfg)
            self.rack_zone_names.append(zone_name)

    def _build_rack_zone(self, zone_name: str, zcfg: RackZoneConfig):
        sx, sy = zcfg.pos
        w, h = zcfg.height, zcfg.width
        gs = self.config.grid_size

        for row_idx in range(zcfg.num_rows):
            rack_y = sy + row_idx * 2
            aisle_y = sy + row_idx * 2 + 1

            # 绘制该行储位（跳过 sub_aisle_cols 列）
            for bay in range(zcfg.bays_per_row):
                bay_x = sx + bay
                if bay_x >= gs or rack_y >= gs:
                    continue
                sname = f"{zone_name}_R{row_idx + 1}_B{bay + 1}"
                self.zone_pos[sname] = (bay_x, rack_y)
                self.storage_list.append(sname)
                self.grid[rack_y, bay_x] = MAP_STORAGE

            # 绘制巷道（↓ ↑ 交替）
            if aisle_y < gs:
                direction = "down" if row_idx % 2 == 0 else "up"
                cell_type = MAP_AISLE_DOWN if direction == "down" else MAP_AISLE_UP
                for bay in range(zcfg.bays_per_row):
                    bay_x = sx + bay
                    if bay_x < gs:
                        self.grid[aisle_y, bay_x] = cell_type
                aid = f"{zone_name}_A{row_idx + 1}"
                self.aisle_info[aid] = AisleConfig(
                    aisle_id=aid, direction=direction, y_offset=aisle_y,
                )

        # 子通道（纵向，贯穿所有行）
        for col_offset in zcfg.sub_aisle_cols:
            col_x = sx + col_offset - 1
            if col_x < 0 or col_x >= gs:
                continue
            for row_idx in range(zcfg.num_rows):
                # 子通道穿过储位行和巷道行
                rack_y = sy + row_idx * 2
                aisle_y = sy + row_idx * 2 + 1
                if rack_y < gs:
                    self.grid[rack_y, col_x] = MAP_SUB_AISLE
                if aisle_y < gs:
                    self.grid[aisle_y, col_x] = MAP_SUB_AISLE

    def is_passable(self, x: int, y: int, dx: int = 0, dy: int = 0) -> bool:
        gs = self.config.grid_size
        if not (0 <= x < gs and 0 <= y < gs):
            return False
        cell = self.grid[y, x]
        if cell == MAP_OBSTACLE:
            return False
        if cell == MAP_AISLE_DOWN:
            if dy < 0:
                return False
        if cell == MAP_AISLE_UP:
            if dy > 0:
                return False
        return True

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
