# tests/warehouse/test_map_builder.py
import numpy as np
import pytest
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap, MAP_PASSABLE, MAP_PORT, MAP_WAREHOUSE

import src.warehouse.maps.medium_50x50  # noqa: F401


@pytest.fixture
def medium_map():
    cfg = MapRegistry.get("medium_50x50")
    return WarehouseMap(cfg)


def test_grid_shape(medium_map):
    assert medium_map.grid.shape == (50, 50)


def test_zone_pos_populated(medium_map):
    # 12个仓库区 + 每个区4个储位(48) + 4个端口 + 12个避让点 + 4个充电桩
    assert len(medium_map.zone_pos) >= 60
    assert "Raw1" in medium_map.zone_pos
    assert "入库北" in medium_map.zone_pos
    assert "Raw1_S1" in medium_map.zone_pos


def test_storage_list(medium_map):
    assert len(medium_map.storage_list) == 48  # 12 zones × 4 storages


def test_ports(medium_map):
    assert len(medium_map.port_info) == 4
    assert medium_map.port_info["入库北"]["type"] == "INBOUND"


def test_charging_points(medium_map):
    assert len(medium_map.charging_points) == 4
    assert (4, 4) in medium_map.charging_points


def test_is_passable(medium_map):
    # 通道应该可通行
    assert medium_map.is_passable(8, 6) is True
    # (0,0) 应该是障碍
    assert medium_map.is_passable(0, 0) is False
    # 越界
    assert medium_map.is_passable(100, 100) is False


def test_grid_port_area(medium_map):
    # 入库北区域 (18,26,2,6) → x1=18,x2=26,y1=2,y2=6
    assert medium_map.grid[3, 20] == MAP_PORT


def test_warehouse_zone_internal_channels(medium_map):
    # Raw1: pos=(6,8), w=6, h=5
    # 内部通道 y=sy+2=10, x=sx~sx+6
    assert medium_map.grid[10, 8] == MAP_PASSABLE  # 水平通道
    assert medium_map.grid[9, 9] == MAP_PASSABLE    # 垂直通道 (sx+3=9)


def test_distance_matrix(medium_map):
    dm = medium_map.get_distance_matrix()
    assert len(dm) > 0
    # Raw1 和 Raw2 应该有距离
    key = "Raw1_Raw2"
    assert key in dm
    assert dm[key] > 0
