# src/warehouse/fleet/map_builder.py
"""仓库地图构建器

从MapConfig构建网格地图, 注册所有储位/端口/充电桩的坐标映射(zone_pos)。
货架布局: 每个区域含多行货架, 每行4组×3个储位, 行间有通道供AGV通行。
端口支持多泊位(berths), AGV按ID取模分配泊位避免聚集。
"""

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
        gw = map_config.grid_size
        gh = map_config.grid_height or gw
        self.grid: np.ndarray = np.zeros((gh, gw), dtype=int)
        self.zone_pos: dict[str, tuple[int, int]] = {}
        self.port_info: dict[str, dict] = {}
        self.storage_list: list[str] = []
        self.rack_zone_names: list[str] = []
        self.charging_points: list[tuple[int, int]] = []
        self._build()

    def _build(self):
        cfg = self.config
        gw = cfg.grid_size
        gh = cfg.grid_height or gw

        # 1. 初始化全通道
        self.grid[1:gh - 1, 1:gw - 1] = MAP_PASSABLE

        # 2. 端口
        for port_name, pcfg in cfg.ports.items():
            x1, x2, y1, y2 = pcfg["area"]
            self.grid[y1:y2, x1:x2] = MAP_PORT
            self.zone_pos[port_name] = pcfg["pos"]
            self.port_info[port_name] = pcfg
            # 注册每个泊位到 zone_pos
            for bi, bp in enumerate(pcfg.get("berths", [pcfg["pos"]])):
                self.zone_pos[f"{port_name}_B{bi}"] = bp

        # 3. 充电桩
        for pos in cfg.charging_points:
            x, y = pos
            if 0 <= x < gw and 0 <= y < gh:
                self.grid[y, x] = MAP_CHARGING
                self.zone_pos[f"Charge_{pos}"] = pos
                self.charging_points.append(pos)

        # 4. 货架区域
        for zone_name, zone_cfg in cfg.rack_zones.items():
            self._build_rack_zone(zone_name, zone_cfg)
            self.rack_zone_names.append(zone_name)

    def _build_rack_zone(self, zone_name: str, zcfg: RackZoneConfig):
        """构建单个货架区域: 每行4组×3个储位, 行间间隔1行通道"""
        sx, sy = zcfg.pos
        gw = self.config.grid_size
        gh = self.config.grid_height or gw

        group_width = 4
        num_groups = 4
        row_pairs = min(zcfg.height // 2, 5)

        for row_idx in range(row_pairs):
            rack_y = sy + row_idx * 2

            for g in range(num_groups):
                for s in range(3):
                    bay_x = sx + g * group_width + s
                    if bay_x >= gw or rack_y >= gh:
                        continue
                    sname = f"{zone_name}_R{row_idx + 1}_B{g * 3 + s + 1}"
                    self.zone_pos[sname] = (bay_x, rack_y)
                    self.storage_list.append(sname)
                    self.grid[rack_y, bay_x] = MAP_STORAGE

    def get_port_berth(self, port_name: str, agv_id: int) -> tuple[int, int]:
        """根据 AGV ID 返回端口内的泊位位置（3个泊位轮询）"""
        pcfg = self.port_info.get(port_name)
        if pcfg is None:
            return self.zone_pos.get(port_name, (0, 0))
        berths = pcfg.get("berths", [pcfg["pos"]])
        return berths[(agv_id - 1) % len(berths)]

    def is_passable(self, x: int, y: int) -> bool:
        gw = self.config.grid_size
        gh = self.config.grid_height or gw
        if not (0 <= x < gw and 0 <= y < gh):
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
