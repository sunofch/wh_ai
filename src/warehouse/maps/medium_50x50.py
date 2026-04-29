# src/warehouse/maps/medium_50x50.py
"""港口备件仓库 50x50 — 9区域行列式货架，6端口对称布局"""

from src.warehouse.maps.base import MapRegistry, BaseMap
from src.warehouse.models import MapConfig, RackZoneConfig


@MapRegistry.register("medium_50x50")
class Medium50x50(BaseMap):
    def build(self) -> MapConfig:
        return MapConfig(
            name="medium_50x50",
            display_name="港口备件仓库 (50×50)",
            grid_size=50,
            description="行列式货架仓，9区域，6端口，主通道3格双向+巷道1格单向",
            main_aisle_width=3,
            sub_aisle_width=1,
            main_channels_x=[16, 17, 18, 32, 33, 34],
            main_channels_y=[5, 6, 7, 18, 19, 20, 31, 32, 33, 44, 45, 46],
            rack_zones={
                "Mech1": RackZoneConfig(zone_id="Mech1", zone_type="mechanical", pos=(2, 8), color="#FF7F0E"),
                "Elec1": RackZoneConfig(zone_id="Elec1", zone_type="electrical", pos=(19, 8), color="#4FC3F7"),
                "Mech2": RackZoneConfig(zone_id="Mech2", zone_type="mechanical", pos=(35, 8), color="#FF9E4A"),
                "Elec2": RackZoneConfig(zone_id="Elec2", zone_type="electrical", pos=(2, 21), color="#0288D1"),
                "Cons1": RackZoneConfig(zone_id="Cons1", zone_type="consumable", pos=(19, 21), color="#2CA02C"),
                "Cons2": RackZoneConfig(zone_id="Cons2", zone_type="consumable", pos=(35, 21), color="#54C954"),
                "Safety": RackZoneConfig(zone_id="Safety", zone_type="safety", pos=(2, 35), color="#9467BD"),
                "Tool": RackZoneConfig(zone_id="Tool", zone_type="tool", pos=(19, 35), color="#8C564B"),
                "Cons3": RackZoneConfig(zone_id="Cons3", zone_type="consumable", pos=(35, 35), color="#7CD97C"),
            },
            ports={
                "IN-L": {"pos": (9, 3), "area": (2, 15, 2, 4), "type": "INBOUND"},
                "IN-C": {"pos": (25, 3), "area": (19, 31, 2, 4), "type": "INBOUND"},
                "IN-R": {"pos": (41, 3), "area": (35, 47, 2, 4), "type": "INBOUND"},
                "OUT-L": {"pos": (9, 48), "area": (2, 15, 47, 49), "type": "OUTBOUND"},
                "OUT-C": {"pos": (25, 48), "area": (19, 31, 47, 49), "type": "OUTBOUND"},
                "OUT-R": {"pos": (41, 48), "area": (35, 47, 47, 49), "type": "OUTBOUND"},
            },
            agv_init_positions=[
                (9, 6), (25, 6), (41, 6),
                (9, 19), (25, 19), (41, 19),
                (9, 45), (25, 45),
            ],
            agv_count=8,
            conflict_segments={},
            yield_points={},
            charging_points=[(2, 2), (47, 2), (2, 47), (47, 47)],
        )
