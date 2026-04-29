# tests/warehouse/test_pathfinding.py
"""寻路测试 — 时空A* + 方向约束"""

from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.pathfinding import PathFinder
from src.warehouse.wms.config import WarehouseConfig
import src.warehouse.maps.medium_50x50


def _make_pf():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    return PathFinder(wmap, config), wmap


def test_path_between_ports():
    pf, wmap = _make_pf()
    start = wmap.port_info["IN-L"]["pos"]
    end = wmap.port_info["OUT-L"]["pos"]
    path, dist = pf.find_base_path(start, end)
    assert len(path) > 1
    assert dist > 0


def test_path_to_storage():
    pf, wmap = _make_pf()
    start = wmap.port_info["IN-C"]["pos"]
    end = wmap.zone_pos["Cons1_R1_B1"]
    path, dist = pf.find_base_path(start, end)
    assert len(path) > 1


def test_path_cross_zone():
    pf, wmap = _make_pf()
    start = wmap.zone_pos["Mech1_R1_B1"]
    end = wmap.zone_pos["Cons3_R5_B10"]
    path, dist = pf.find_base_path(start, end)
    assert len(path) > 1


def test_get_distance():
    pf, wmap = _make_pf()
    d = pf.get_distance(
        wmap.port_info["IN-L"]["pos"],
        wmap.port_info["OUT-R"]["pos"],
    )
    assert d > 0


def test_same_point():
    pf, wmap = _make_pf()
    start = wmap.port_info["IN-L"]["pos"]
    path, dist = pf.find_base_path(start, start)
    assert len(path) == 1
    assert dist == 0


def test_path_to_all_zones():
    """Each zone's first storage should be reachable from a port"""
    pf, wmap = _make_pf()
    start = wmap.port_info["IN-C"]["pos"]
    for zone in wmap.rack_zone_names:
        first_storage = f"{zone}_R1_B1"
        if first_storage in wmap.zone_pos:
            path, dist = pf.find_base_path(start, wmap.zone_pos[first_storage])
            assert len(path) > 1, f"No path to {first_storage}"


def test_distance_symmetry():
    pf, wmap = _make_pf()
    a = wmap.port_info["IN-L"]["pos"]
    b = wmap.port_info["OUT-R"]["pos"]
    assert pf.get_distance(a, b) == pf.get_distance(b, a)
