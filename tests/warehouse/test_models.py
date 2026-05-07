# tests/warehouse/test_models.py
"""数据模型测试 — RackZoneConfig/MapConfig"""

from src.warehouse.models import (
    RackZoneConfig, MapConfig,
)


def test_rack_zone_config_defaults():
    zone = RackZoneConfig(zone_id="Mech1", zone_type="mechanical", pos=(2, 8))
    assert zone.width == 14
    assert zone.height == 10


def test_rack_zone_config_custom():
    zone = RackZoneConfig(
        zone_id="Test", zone_type="tool", pos=(0, 0),
        width=20, height=15,
    )
    assert zone.width == 20


def test_map_config_has_rack_zones():
    zone = RackZoneConfig(zone_id="Test", zone_type="tool", pos=(0, 0))
    cfg = MapConfig(
        name="test", display_name="test", grid_size=50,
        rack_zones={"Test": zone},
    )
    assert "Test" in cfg.rack_zones


def test_map_config_no_warehouse_zones():
    cfg = MapConfig(name="test", display_name="test", grid_size=50)
    assert not hasattr(cfg, "warehouse_zones")
