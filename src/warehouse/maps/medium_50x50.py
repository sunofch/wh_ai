# src/warehouse/maps/medium_50x50.py
"""中型50x50地图预设"""

from src.warehouse.maps.base import MapRegistry, BaseMap
from src.warehouse.models import MapConfig


@MapRegistry.register("medium_50x50")
class Medium50x50(BaseMap):
    def build(self) -> MapConfig:
        return MapConfig(
            name="medium_50x50",
            display_name="中型仓库 (50×50)",
            grid_size=50,
            description="默认中规模测试地图，12个仓库区，4个端口，8台AGV",
            main_channels_x=[8, 15, 22, 29, 36, 43],
            main_channels_y=[6, 15, 22, 30, 38, 44],
            warehouse_zones={
                "Raw1": {"pos": (6, 8), "w": 6, "h": 5, "color": "#FF7F0E"},
                "Raw2": {"pos": (14, 8), "w": 6, "h": 5, "color": "#FF9E4A"},
                "Finished1": {"pos": (6, 24), "w": 6, "h": 5, "color": "#2CA02C"},
                "Finished2": {"pos": (14, 24), "w": 6, "h": 5, "color": "#54C954"},
                "Finished3": {"pos": (28, 24), "w": 6, "h": 5, "color": "#7CD97C"},
                "Finished4": {"pos": (36, 24), "w": 6, "h": 5, "color": "#A5E9A5"},
                "Spare1": {"pos": (28, 8), "w": 6, "h": 5, "color": "#D62728"},
                "Spare2": {"pos": (36, 8), "w": 6, "h": 5, "color": "#E96363"},
                "Spare3": {"pos": (6, 38), "w": 6, "h": 5, "color": "#9467BD"},
                "Spare4": {"pos": (14, 38), "w": 6, "h": 5, "color": "#B191D1"},
                "Spare5": {"pos": (28, 38), "w": 6, "h": 5, "color": "#8C564B"},
                "Spare6": {"pos": (36, 38), "w": 6, "h": 5, "color": "#A67C52"},
            },
            ports={
                "入库北": {"pos": (22, 4), "area": (18, 26, 2, 6), "type": "INBOUND"},
                "出库南": {"pos": (22, 46), "area": (18, 26, 44, 48), "type": "OUTBOUND"},
                "紧急出库西": {"pos": (4, 22), "area": (2, 6, 18, 26), "type": "OUTBOUND"},
                "备件入库东": {"pos": (46, 22), "area": (44, 48, 18, 26), "type": "INBOUND"},
            },
            agv_init_positions=[
                (8, 6), (22, 6), (36, 6), (8, 22),
                (22, 22), (36, 22), (8, 38), (22, 38),
            ],
            agv_count=8,
            conflict_segments={
                "seg_h1": {
                    "start": (8, 15), "end": (36, 15), "length": 28,
                    "yield_points": ["yp_A", "yp_B", "yp_C"], "direction": "RIGHT",
                },
                "seg_h2": {
                    "start": (8, 30), "end": (36, 30), "length": 28,
                    "yield_points": ["yp_D", "yp_E", "yp_F"], "direction": "RIGHT",
                },
                "seg_v1": {
                    "start": (15, 8), "end": (15, 36), "length": 28,
                    "yield_points": ["yp_G", "yp_H", "yp_I"], "direction": "DOWN",
                },
                "seg_v2": {
                    "start": (29, 8), "end": (29, 36), "length": 28,
                    "yield_points": ["yp_J", "yp_K", "yp_L"], "direction": "DOWN",
                },
            },
            yield_points={
                "yp_A": (8, 15), "yp_B": (22, 15), "yp_C": (36, 15),
                "yp_D": (8, 30), "yp_E": (22, 30), "yp_F": (36, 30),
                "yp_G": (15, 8), "yp_H": (15, 22), "yp_I": (15, 36),
                "yp_J": (29, 8), "yp_K": (29, 22), "yp_L": (29, 36),
            },
            charging_points=[(4, 4), (46, 4), (4, 46), (46, 46)],
        )
