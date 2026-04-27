# tests/warehouse/test_charging.py
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.pathfinding import PathFinder
from src.warehouse.fleet.charging import ChargingScheduler
from src.warehouse.wms.config import WarehouseConfig

import src.warehouse.maps.medium_50x50  # noqa: F401


def test_plan_charging():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    pf = PathFinder(wmap, config)
    cs = ChargingScheduler(pf, wmap, config)
    path, end_t, charge_pos = cs.plan_charging((8, 6), 100)
    assert charge_pos in wmap.charging_points
    assert end_t > 100


def test_estimate_battery():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    pf = PathFinder(wmap, config)
    cs = ChargingScheduler(pf, wmap, config)
    assert cs.estimate_battery_usage(10) == 10


def test_need_charge():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    pf = PathFinder(wmap, config)
    cs = ChargingScheduler(pf, wmap, config)
    assert cs.need_charge(25, 0) is False
    assert cs.need_charge(15, 10) is True
