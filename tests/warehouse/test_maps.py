# tests/warehouse/test_maps.py
"""地图预设测试 — medium_57x47 注册和配置验证"""

from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47


def test_medium_registered():
    cfg = MapRegistry.get("medium_57x47")
    assert cfg.grid_size == 57
    assert len(cfg.rack_zones) == 9
    assert len(cfg.ports) == 6
    assert cfg.agv_count == 8
    assert len(cfg.charging_points) == 4


def test_port_types():
    cfg = MapRegistry.get("medium_57x47")
    inbound = [n for n, c in cfg.ports.items() if c["type"] == "INBOUND"]
    outbound = [n for n, c in cfg.ports.items() if c["type"] == "OUTBOUND"]
    assert len(inbound) == 3
    assert len(outbound) == 3


def test_zone_types():
    cfg = MapRegistry.get("medium_57x47")
    types = [z.zone_type for z in cfg.rack_zones.values()]
    assert types.count("mechanical") == 2
    assert types.count("electrical") == 2
    assert types.count("consumable") == 3
    assert types.count("safety") == 1
    assert types.count("tool") == 1
