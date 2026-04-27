# tests/warehouse/test_maps.py
import pytest
from src.warehouse.maps.base import MapRegistry, BaseMap
from src.warehouse.models import MapConfig

# 触发注册
import src.warehouse.maps.medium_50x50  # noqa: F401


def test_medium_map_registered():
    assert "medium_50x50" in MapRegistry._maps


def test_medium_map_config():
    cfg = MapRegistry.get("medium_50x50")
    assert isinstance(cfg, MapConfig)
    assert cfg.grid_size == 50
    assert cfg.agv_count == 8
    assert len(cfg.warehouse_zones) == 12
    assert len(cfg.ports) == 4
    assert len(cfg.conflict_segments) == 4
    assert len(cfg.yield_points) == 12
    assert len(cfg.charging_points) == 4
    assert len(cfg.agv_init_positions) == 8


def test_list_all():
    maps = MapRegistry.list_all()
    assert len(maps) >= 1
    names = [m[0] for m in maps]
    assert "medium_50x50" in names


def test_get_unknown_map_raises():
    with pytest.raises(ValueError, match="未注册"):
        MapRegistry.get("nonexistent_map")


def test_register_custom_map():
    @MapRegistry.register("test_tiny")
    class TinyMap(BaseMap):
        def build(self) -> MapConfig:
            return MapConfig(name="test_tiny", display_name="Tiny", grid_size=5)

    cfg = MapRegistry.get("test_tiny")
    assert cfg.grid_size == 5
    # 清理
    del MapRegistry._maps["test_tiny"]


# ── 追加：大型地图和极端地图测试 ──

import src.warehouse.maps.large_100x100  # noqa: F401
import src.warehouse.maps.extreme  # noqa: F401
from src.warehouse.fleet.map_builder import WarehouseMap


def test_all_maps_registered():
    expected = ["medium_50x50", "large_100x100", "extreme_corner", "extreme_corridor", "extreme_cluster"]
    for name in expected:
        assert name in MapRegistry._maps, f"Map '{name}' not registered"


def test_large_map_config():
    cfg = MapRegistry.get("large_100x100")
    assert cfg.grid_size == 100
    assert cfg.agv_count == 20
    assert len(cfg.warehouse_zones) == 24
    assert len(cfg.ports) == 8


def test_extreme_corner_config():
    cfg = MapRegistry.get("extreme_corner")
    assert cfg.grid_size == 50
    assert len(cfg.warehouse_zones) == 12


def test_extreme_corridor_config():
    cfg = MapRegistry.get("extreme_corridor")
    assert cfg.grid_size == 50
    assert len(cfg.conflict_segments) == 2  # 瓶颈


def test_extreme_cluster_config():
    cfg = MapRegistry.get("extreme_cluster")
    assert cfg.grid_size == 50
    assert len(cfg.warehouse_zones) == 12


def test_all_maps_buildable():
    """所有地图都能成功构建WarehouseMap"""
    for name, _ in MapRegistry.list_all():
        cfg = MapRegistry.get(name)
        wmap = WarehouseMap(cfg)
        assert wmap.grid.shape == (cfg.grid_size, cfg.grid_size)
        assert len(wmap.zone_pos) > 0
