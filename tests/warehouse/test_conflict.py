# tests/warehouse/test_conflict.py
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.pathfinding import PathFinder
from src.warehouse.fleet.conflict import ConflictManager
from src.warehouse.wms.config import WarehouseConfig

import src.warehouse.maps.medium_50x50  # noqa: F401


def test_segments_created():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    pf = PathFinder(wmap, WarehouseConfig())
    cm = ConflictManager(wmap, pf.st_table)
    assert len(cm.segments) == 4


def test_request_segment_free():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    pf = PathFinder(wmap, WarehouseConfig())
    cm = ConflictManager(wmap, pf.st_table)
    assert cm.request_segment(1, "seg_h1", "RIGHT", 0) is True


def test_request_segment_opposite():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    pf = PathFinder(wmap, WarehouseConfig())
    cm = ConflictManager(wmap, pf.st_table)
    cm.request_segment(1, "seg_h1", "RIGHT", 0)
    assert cm.request_segment(2, "seg_h1", "LEFT", 0) is False


def test_release_segment():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    pf = PathFinder(wmap, WarehouseConfig())
    cm = ConflictManager(wmap, pf.st_table)
    cm.request_segment(1, "seg_h1", "RIGHT", 0)
    cm.release_segment(1, "seg_h1")
    assert cm.segments["seg_h1"].is_occupied is False
