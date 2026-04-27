# src/warehouse/maps/extreme.py
"""极端分布地图预设（三个变体）"""

from src.warehouse.maps.base import MapRegistry, BaseMap
from src.warehouse.models import MapConfig


def _medium_base() -> dict:
    """共享50x50基础配置"""
    return {
        "grid_size": 50,
        "main_channels_x": [8, 15, 22, 29, 36, 43],
        "main_channels_y": [6, 15, 22, 30, 38, 44],
        "ports": {
            "入库北": {"pos": (22, 4), "area": (18, 26, 2, 6), "type": "INBOUND"},
            "出库南": {"pos": (22, 46), "area": (18, 26, 44, 48), "type": "OUTBOUND"},
            "紧急出库西": {"pos": (4, 22), "area": (2, 6, 18, 26), "type": "OUTBOUND"},
            "备件入库东": {"pos": (46, 22), "area": (44, 48, 18, 26), "type": "INBOUND"},
        },
        "conflict_segments": {
            "seg_h1": {"start": (8, 15), "end": (36, 15), "length": 28,
                       "yield_points": ["yp_A", "yp_B", "yp_C"], "direction": "RIGHT"},
            "seg_h2": {"start": (8, 30), "end": (36, 30), "length": 28,
                       "yield_points": ["yp_D", "yp_E", "yp_F"], "direction": "RIGHT"},
            "seg_v1": {"start": (15, 8), "end": (15, 36), "length": 28,
                       "yield_points": ["yp_G", "yp_H", "yp_I"], "direction": "DOWN"},
            "seg_v2": {"start": (29, 8), "end": (29, 36), "length": 28,
                       "yield_points": ["yp_J", "yp_K", "yp_L"], "direction": "DOWN"},
        },
        "yield_points": {
            "yp_A": (8, 15), "yp_B": (22, 15), "yp_C": (36, 15),
            "yp_D": (8, 30), "yp_E": (22, 30), "yp_F": (36, 30),
            "yp_G": (15, 8), "yp_H": (15, 22), "yp_I": (15, 36),
            "yp_J": (29, 8), "yp_K": (29, 22), "yp_L": (29, 36),
        },
        "charging_points": [(4, 4), (46, 4), (4, 46), (46, 46)],
        "agv_count": 8,
        "agv_init_positions": [(8, 6), (22, 6), (36, 6), (8, 22),
                               (22, 22), (36, 22), (8, 38), (22, 38)],
    }


@MapRegistry.register("extreme_corner")
class ExtremeCorner(BaseMap):
    """仓库集中在四角"""
    def build(self) -> MapConfig:
        base = _medium_base()
        return MapConfig(
            name="extreme_corner", display_name="极端-四角集中 (50×50)",
            grid_size=base["grid_size"],
            description="仓库集中在四角，AGV需穿越中心",
            main_channels_x=base["main_channels_x"],
            main_channels_y=base["main_channels_y"],
            warehouse_zones={
                "Raw1": {"pos": (4, 4), "w": 6, "h": 5, "color": "#FF7F0E"},
                "Raw2": {"pos": (40, 4), "w": 6, "h": 5, "color": "#FF9E4A"},
                "Finished1": {"pos": (4, 40), "w": 6, "h": 5, "color": "#2CA02C"},
                "Finished2": {"pos": (40, 40), "w": 6, "h": 5, "color": "#54C954"},
                "Spare1": {"pos": (4, 10), "w": 6, "h": 5, "color": "#D62728"},
                "Spare2": {"pos": (40, 10), "w": 6, "h": 5, "color": "#E96363"},
                "Finished3": {"pos": (4, 34), "w": 6, "h": 5, "color": "#7CD97C"},
                "Finished4": {"pos": (40, 34), "w": 6, "h": 5, "color": "#A5E9A5"},
                "Raw3": {"pos": (10, 4), "w": 6, "h": 5, "color": "#FFB57A"},
                "Raw4": {"pos": (34, 4), "w": 6, "h": 5, "color": "#FFCFA0"},
                "Spare3": {"pos": (10, 40), "w": 6, "h": 5, "color": "#9467BD"},
                "Spare4": {"pos": (34, 40), "w": 6, "h": 5, "color": "#B191D1"},
            },
            ports=base["ports"],
            agv_init_positions=base["agv_init_positions"],
            agv_count=base["agv_count"],
            conflict_segments=base["conflict_segments"],
            yield_points=base["yield_points"],
            charging_points=base["charging_points"],
        )


@MapRegistry.register("extreme_corridor")
class ExtremeCorridor(BaseMap):
    """单通道瓶颈"""
    def build(self) -> MapConfig:
        base = _medium_base()
        return MapConfig(
            name="extreme_corridor", display_name="极端-单通道瓶颈 (50×50)",
            grid_size=base["grid_size"],
            description="仅有两条冲突路段，单通道瓶颈",
            main_channels_x=base["main_channels_x"],
            main_channels_y=base["main_channels_y"],
            warehouse_zones={
                "Raw1": {"pos": (6, 8), "w": 6, "h": 5, "color": "#FF7F0E"},
                "Raw2": {"pos": (36, 8), "w": 6, "h": 5, "color": "#FF9E4A"},
                "Finished1": {"pos": (6, 24), "w": 6, "h": 5, "color": "#2CA02C"},
                "Finished2": {"pos": (36, 24), "w": 6, "h": 5, "color": "#54C954"},
                "Finished3": {"pos": (6, 38), "w": 6, "h": 5, "color": "#7CD97C"},
                "Finished4": {"pos": (36, 38), "w": 6, "h": 5, "color": "#A5E9A5"},
                "Spare1": {"pos": (20, 8), "w": 6, "h": 5, "color": "#D62728"},
                "Spare2": {"pos": (20, 38), "w": 6, "h": 5, "color": "#E96363"},
            },
            ports=base["ports"],
            agv_init_positions=base["agv_init_positions"],
            agv_count=base["agv_count"],
            conflict_segments={
                "seg_h1": {"start": (8, 22), "end": (42, 22), "length": 34,
                           "yield_points": ["yp_A", "yp_B"], "direction": "RIGHT"},
                "seg_v1": {"start": (22, 8), "end": (22, 42), "length": 34,
                           "yield_points": ["yp_C", "yp_D"], "direction": "DOWN"},
            },
            yield_points={
                "yp_A": (8, 22), "yp_B": (42, 22),
                "yp_C": (22, 8), "yp_D": (22, 42),
            },
            charging_points=base["charging_points"],
        )


@MapRegistry.register("extreme_cluster")
class ExtremeCluster(BaseMap):
    """储位高度集中"""
    def build(self) -> MapConfig:
        base = _medium_base()
        return MapConfig(
            name="extreme_cluster", display_name="极端-高度集中 (50×50)",
            grid_size=base["grid_size"],
            description="储位集中在中间区域，长距离搬运",
            main_channels_x=base["main_channels_x"],
            main_channels_y=base["main_channels_y"],
            warehouse_zones={
                "Raw1": {"pos": (14, 14), "w": 6, "h": 5, "color": "#FF7F0E"},
                "Raw2": {"pos": (22, 14), "w": 6, "h": 5, "color": "#FF9E4A"},
                "Finished1": {"pos": (14, 22), "w": 6, "h": 5, "color": "#2CA02C"},
                "Finished2": {"pos": (22, 22), "w": 6, "h": 5, "color": "#54C954"},
                "Finished3": {"pos": (30, 22), "w": 6, "h": 5, "color": "#7CD97C"},
                "Finished4": {"pos": (14, 30), "w": 6, "h": 5, "color": "#A5E9A5"},
                "Spare1": {"pos": (30, 14), "w": 6, "h": 5, "color": "#D62728"},
                "Spare2": {"pos": (30, 30), "w": 6, "h": 5, "color": "#E96363"},
                "Spare3": {"pos": (14, 8), "w": 6, "h": 5, "color": "#9467BD"},
                "Spare4": {"pos": (30, 8), "w": 6, "h": 5, "color": "#B191D1"},
                "Spare5": {"pos": (14, 36), "w": 6, "h": 5, "color": "#8C564B"},
                "Spare6": {"pos": (30, 36), "w": 6, "h": 5, "color": "#A67C52"},
            },
            ports=base["ports"],
            agv_init_positions=base["agv_init_positions"],
            agv_count=base["agv_count"],
            conflict_segments=base["conflict_segments"],
            yield_points=base["yield_points"],
            charging_points=base["charging_points"],
        )
