# src/warehouse/maps/large_100x100.py
"""大型100x100地图预设"""

from src.warehouse.maps.base import MapRegistry, BaseMap
from src.warehouse.models import MapConfig


@MapRegistry.register("large_100x100")
class Large100x100(BaseMap):
    def build(self) -> MapConfig:
        zones = {}
        zone_configs = [
            ("Raw", [(6,8), (14,8), (22,8), (30,8), (6,38), (14,38), (22,38), (30,38)]),
            ("Finished", [(6,24), (14,24), (22,24), (30,24), (52,24), (60,24), (68,24), (76,24)]),
            ("Spare", [(52,8), (60,8), (68,8), (76,8), (52,38), (60,38), (68,38), (76,38)]),
        ]
        colors_map = {
            "Raw": ["#FF7F0E", "#FF9E4A", "#FFB57A", "#FFCFA0",
                    "#E07010", "#E88A3A", "#F0A464", "#F8BE8E"],
            "Finished": ["#2CA02C", "#54C954", "#7CD97C", "#A5E9A5",
                         "#3CB03C", "#64D964", "#8CE98C", "#B5F9B5"],
            "Spare": ["#D62728", "#E96363", "#FC9F9F", "#FFBBBB",
                      "#9467BD", "#B191D1", "#CEBBE5", "#EBE5F9"],
        }
        idx = 0
        for zone_type, positions in zone_configs:
            for i, (px, py) in enumerate(positions):
                idx += 1
                name = f"{zone_type}{idx}"
                colors = colors_map[zone_type]
                zones[name] = {"pos": (px, py), "w": 6, "h": 5,
                               "color": colors[i % len(colors)]}

        channels_x = [8, 15, 22, 29, 36, 43, 50, 57, 64, 71, 78, 85]
        channels_y = [6, 15, 22, 30, 38, 44, 52, 60, 68, 76, 84, 94]

        segs = {}
        yp = {}
        for i, y in enumerate([15, 38, 60, 84]):
            yp_names = [f"yp_h{i+1}_{j}" for j in range(3)]
            yp.update({n: (x, y) for n, x in zip(yp_names, [15, 50, 85])})
            segs[f"seg_h{i+1}"] = {
                "start": (15, y), "end": (85, y), "length": 70,
                "yield_points": yp_names, "direction": "RIGHT",
            }
        for i, x in enumerate([36, 71]):
            yp_names = [f"yp_v{i+1}_{j}" for j in range(3)]
            yp.update({n: (x, y) for n, y in zip(yp_names, [15, 50, 85])})
            segs[f"seg_v{i+1}"] = {
                "start": (x, 15), "end": (x, 85), "length": 70,
                "yield_points": yp_names, "direction": "DOWN",
            }

        agv_pos = [(8,6), (22,6), (36,6), (50,6), (64,6), (78,6),
                   (8,22), (22,22), (36,22), (50,22), (64,22), (78,22),
                   (8,44), (22,44), (36,44), (50,44), (64,44), (78,44),
                   (8,60), (22,60)]

        ports = {
            "入库北": {"pos": (50, 4), "area": (46,54,2,6), "type": "INBOUND"},
            "出库南": {"pos": (50, 96), "area": (46,54,94,98), "type": "OUTBOUND"},
            "紧急出库西": {"pos": (4, 50), "area": (2,6,46,54), "type": "OUTBOUND"},
            "备件入库东": {"pos": (96, 50), "area": (94,98,46,54), "type": "INBOUND"},
            "入库西北": {"pos": (20, 4), "area": (16,24,2,6), "type": "INBOUND"},
            "出库东南": {"pos": (80, 96), "area": (76,84,94,98), "type": "OUTBOUND"},
            "紧急出库南": {"pos": (4, 80), "area": (2,6,76,84), "type": "OUTBOUND"},
            "备件入库北": {"pos": (96, 20), "area": (94,98,16,24), "type": "INBOUND"},
        }

        return MapConfig(
            name="large_100x100", display_name="大型仓库 (100×100)", grid_size=100,
            description="大规模压力测试地图，24个仓库区，8个端口，20台AGV",
            main_channels_x=channels_x, main_channels_y=channels_y,
            warehouse_zones=zones, ports=ports,
            agv_init_positions=agv_pos, agv_count=20,
            conflict_segments=segs, yield_points=yp,
            charging_points=[(4,4), (96,4), (4,96), (96,96),
                             (4,50), (96,50), (50,4), (50,96)],
        )
