# src/warehouse/maps/medium_57x47_cluster.py
"""港口备件仓库 57×47 — AGV聚集场景

与 medium_57x47 相同布局，但 8 台 AGV 全部集中在仓库左侧:
  - 4 台在上排通道 (y=5-6, x=4 和 x=23)
  - 4 台在中排通道 (y=16-17, x=4 和 x=23)

用于测试高密度 AGV 聚集场景下的调度和路径冲突处理。
"""

from src.warehouse.maps.base import MapRegistry, BaseMap
from src.warehouse.models import MapConfig, RackZoneConfig


@MapRegistry.register("medium_57x47_cluster")
class Medium57x47Cluster(BaseMap):
    def build(self) -> MapConfig:
        return MapConfig(
            name="medium_57x47_cluster",
            display_name="港口备件仓库 (57×47 AGV聚集)",
            grid_size=57,
            grid_height=47,
            description="行列式货架仓，9区域，6端口，8台AGV聚集在左侧",
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
                "IN-L": {"pos": (10, 3), "area": (3, 18, 2, 4), "type": "INBOUND",
                         "berths": [(6, 3), (10, 3), (14, 3)]},
                "IN-C": {"pos": (28, 3), "area": (21, 36, 2, 4), "type": "INBOUND",
                         "berths": [(24, 3), (28, 3), (32, 3)]},
                "IN-R": {"pos": (46, 3), "area": (39, 54, 2, 4), "type": "INBOUND",
                         "berths": [(42, 3), (46, 3), (50, 3)]},
                # 出库端口 (底部, 行43-44)
                "OUT-L": {"pos": (10, 44), "area": (3, 18, 43, 45), "type": "OUTBOUND",
                          "berths": [(6, 44), (10, 44), (14, 44)]},
                "OUT-C": {"pos": (28, 44), "area": (21, 36, 43, 45), "type": "OUTBOUND",
                          "berths": [(24, 44), (28, 44), (32, 44)]},
                "OUT-R": {"pos": (46, 44), "area": (39, 54, 43, 45), "type": "OUTBOUND",
                          "berths": [(42, 44), (46, 44), (50, 44)]},
            },
            # 8台AGV全部聚集在仓库左侧通道
            agv_init_positions=[
                # 上排通道 (y=5-6, 入库端口下方)
                (4, 5), (23, 5),
                (4, 6), (23, 6),
                # 中排通道 (y=16-17, 上排与中排货架之间)
                (4, 16), (23, 16),
                (4, 17), (23, 17),
            ],
            agv_count=8,
            charging_points=[(2, 1), (54, 1), (2, 45), (54, 45)],
        )
