# src/warehouse/maps/medium_57x47.py
"""港口备件仓库 57×47 — 9区域行列式货架，6端口对称布局，全双向通道"""

from src.warehouse.maps.base import MapRegistry, BaseMap
from src.warehouse.models import MapConfig, RackZoneConfig


@MapRegistry.register("medium_57x47")
class Medium57x47(BaseMap):
    def build(self) -> MapConfig:
        # 从 ASCII 地图精确解析
        # 网格: 57×47 (包括边界墙)
        # 货架行: [7,9,11,13,15], [19,21,23,25,27], [31,33,35,37,39]
        # X区域: col 3-17, 21-35, 39-53 (每组 width=15)
        # 每行储位: 4组×3=12个, 共5行, 每区域60个

        return MapConfig(
            name="medium_57x47",
            display_name="港口备件仓库 (57×47 全双向)",
            grid_size=57,
            description="行列式货架仓，9区域，6端口，全双向通道",
            rack_zones={
                # 上排 (Y: 7-15, 5行货架)
                "Mech1": RackZoneConfig(
                    zone_id="Mech1", zone_type="mechanical",
                    pos=(3, 7), width=15, height=10, color="#FF7F0E",
                ),
                "Elec1": RackZoneConfig(
                    zone_id="Elec1", zone_type="electrical",
                    pos=(21, 7), width=15, height=10, color="#4FC3F7",
                ),
                "Mech2": RackZoneConfig(
                    zone_id="Mech2", zone_type="mechanical",
                    pos=(39, 7), width=15, height=10, color="#FF9E4A",
                ),
                # 中排 (Y: 19-27, 5行货架)
                "Elec2": RackZoneConfig(
                    zone_id="Elec2", zone_type="electrical",
                    pos=(3, 19), width=15, height=10, color="#0288D1",
                ),
                "Cons1": RackZoneConfig(
                    zone_id="Cons1", zone_type="consumable",
                    pos=(21, 19), width=15, height=10, color="#2CA02C",
                ),
                "Cons2": RackZoneConfig(
                    zone_id="Cons2", zone_type="consumable",
                    pos=(39, 19), width=15, height=10, color="#54C954",
                ),
                # 下排 (Y: 31-39, 5行货架)
                "Safety": RackZoneConfig(
                    zone_id="Safety", zone_type="safety",
                    pos=(3, 31), width=15, height=10, color="#9467BD",
                ),
                "Tool": RackZoneConfig(
                    zone_id="Tool", zone_type="tool",
                    pos=(21, 31), width=15, height=10, color="#8C564B",
                ),
                "Cons3": RackZoneConfig(
                    zone_id="Cons3", zone_type="consumable",
                    pos=(39, 31), width=15, height=10, color="#7CD97C",
                ),
            },
            ports={
                # 入库端口 (顶部, 行2-3)
                "IN-L": {"pos": (10, 2), "area": (3, 18, 2, 4), "type": "INBOUND"},
                "IN-C": {"pos": (28, 2), "area": (21, 36, 2, 4), "type": "INBOUND"},
                "IN-R": {"pos": (46, 2), "area": (39, 54, 2, 4), "type": "INBOUND"},
                # 出库端口 (底部, 行43-44)
                "OUT-L": {"pos": (10, 44), "area": (3, 18, 43, 45), "type": "OUTBOUND"},
                "OUT-C": {"pos": (28, 44), "area": (21, 36, 43, 45), "type": "OUTBOUND"},
                "OUT-R": {"pos": (46, 44), "area": (39, 54, 43, 45), "type": "OUTBOUND"},
            },
            agv_init_positions=[
                (10, 5), (28, 5), (46, 5),
                (10, 17), (28, 17), (46, 17),
                (10, 42), (28, 42),
            ],
            agv_count=8,
            charging_points=[(2, 1), (54, 1), (2, 45), (54, 45)],
        )
