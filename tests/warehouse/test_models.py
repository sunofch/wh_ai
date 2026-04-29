# tests/warehouse/test_models.py
"""数据模型测试 — RackZoneConfig/RackRow/AisleConfig/MapConfig"""

from src.warehouse.models import (
    RackZoneConfig, RackRow, AisleConfig, MapConfig,
)


def test_rack_zone_config_defaults():
    zone = RackZoneConfig(zone_id="Mech1", zone_type="mechanical", pos=(2, 8))
    assert zone.width == 14
    assert zone.height == 10
    assert zone.num_rows == 5
    assert zone.bays_per_row == 10
    assert zone.sub_aisle_cols == [3, 6, 9, 12]


def test_rack_zone_config_custom():
    zone = RackZoneConfig(
        zone_id="Test", zone_type="tool", pos=(0, 0),
        width=20, height=15, num_rows=7, bays_per_row=15,
        sub_aisle_cols=[5, 10],
    )
    assert zone.width == 20
    assert zone.num_rows == 7


def test_map_config_has_rack_zones():
    zone = RackZoneConfig(zone_id="Test", zone_type="tool", pos=(0, 0))
    cfg = MapConfig(
        name="test", display_name="test", grid_size=50,
        rack_zones={"Test": zone},
    )
    assert "Test" in cfg.rack_zones
    assert cfg.main_aisle_width == 3
    assert cfg.sub_aisle_width == 1


def test_map_config_no_warehouse_zones():
    cfg = MapConfig(name="test", display_name="test", grid_size=50)
    assert not hasattr(cfg, "warehouse_zones")


def test_rack_row():
    row = RackRow(row_id="R1", positions=["A", "B", "C"], y_offset=5)
    assert row.row_id == "R1"
    assert len(row.positions) == 3


def test_aisle_config():
    aisle = AisleConfig(aisle_id="A1", direction="down", y_offset=3)
    assert aisle.direction == "down"
