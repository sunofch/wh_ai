# tests/warehouse/test_pathfinding.py
import pytest
import numpy as np
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.pathfinding import PathFinder, SpaceTimeTable
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.models import AblationFlags

import src.warehouse.maps.medium_50x50  # noqa: F401


@pytest.fixture
def pathfinder():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    return PathFinder(wmap, config)


def test_find_base_path_same_point(pathfinder):
    path, dist = pathfinder.find_base_path((8, 6), (8, 6))
    assert path == [(8, 6)]
    assert dist == 0


def test_find_base_path_adjacent(pathfinder):
    path, dist = pathfinder.find_base_path((8, 6), (8, 7))
    assert len(path) >= 2
    assert dist >= 1


def test_find_base_path_caches(pathfinder):
    p1, d1 = pathfinder.find_base_path((8, 6), (22, 22))
    p2, d2 = pathfinder.find_base_path((8, 6), (22, 22))
    assert p1 == p2
    assert d1 == d2


def test_get_distance(pathfinder):
    d = pathfinder.get_distance((8, 6), (22, 22))
    assert d > 0


def test_get_distance_same_point(pathfinder):
    d = pathfinder.get_distance((8, 6), (8, 6))
    assert d == 0


def test_find_path_basic(pathfinder):
    path, turns, time = pathfinder.find_path(
        (8, 6), (22, 22), 0, 0, 0, 1
    )
    assert len(path) >= 2
    assert time > 0


def test_find_path_same_start_end(pathfinder):
    path, turns, time = pathfinder.find_path(
        (8, 6), (8, 6), 0, 0, 0, 1
    )
    assert path == [(8, 6)]
    assert time == 0


def test_precompute_increases_cache(pathfinder):
    pathfinder.precompute_all_paths()
    # 应该缓存了大量路径
    assert len(pathfinder._path_cache) > 100


def test_space_time_table_occupation():
    st = SpaceTimeTable(50)
    st.lock_occupation(5, 5, 0, 10, 1)
    ok, occ = st.check_occupation(5, 5, 3, 7, 1)
    assert ok is True  # same AGV
    ok2, occ2 = st.check_occupation(5, 5, 3, 7, 2)
    assert ok2 is False  # different AGV


def test_path_calc_count_increases(pathfinder):
    initial = pathfinder.st_table.path_calc_count
    pathfinder.find_base_path((8, 6), (36, 38))
    assert pathfinder.st_table.path_calc_count > initial


def test_cache_disabled():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig(ablation=AblationFlags(enable_path_cache=False))
    pf = PathFinder(wmap, config)
    pf.find_base_path((8, 6), (22, 22))
    assert len(pf._path_cache) == 0  # no caching
