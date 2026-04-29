# tests/warehouse/test_fleet_manager.py
"""Fleet 层测试 — FleetManager 初始化与调度"""

from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.fleet_manager import FleetManager
from src.warehouse.wms.config import WarehouseConfig
import src.warehouse.maps.medium_50x50


def _make_fleet():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    return FleetManager(wmap, config), wmap


def test_fleet_init():
    fleet, _ = _make_fleet()
    assert fleet.path_finder is not None
    assert fleet.tsp is not None
    assert fleet.allocator is not None


def test_precompute():
    fleet, _ = _make_fleet()
    fleet.precompute()
    assert len(fleet.path_finder._dist_cache) > 0
