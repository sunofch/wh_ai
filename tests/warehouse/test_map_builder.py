# tests/warehouse/test_map_builder.py
"""地图构建器测试 — 全双向通道"""

import numpy as np
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import (
    WarehouseMap, MAP_PASSABLE, MAP_PORT, MAP_CHARGING, MAP_STORAGE,
)
import src.warehouse.maps.medium_57x47


def _build_map() -> WarehouseMap:
    cfg = MapRegistry.get("medium_57x47")
    return WarehouseMap(cfg)


def test_zone_names():
    wmap = _build_map()
    expected = {"Mech1", "Elec1", "Mech2", "Elec2", "Cons1", "Cons2", "Safety", "Tool", "Cons3"}
    assert set(wmap.rack_zone_names) == expected


def test_port_cells():
    wmap = _build_map()
    cfg = wmap.config
    for name, pcfg in cfg.ports.items():
        px, py = pcfg["pos"]
        assert wmap.grid[py, px] == MAP_PORT, f"Port {name} at ({px},{py}) not MAP_PORT"


def test_charging_cells():
    wmap = _build_map()
    for cx, cy in wmap.config.charging_points:
        assert wmap.grid[cy, cx] == MAP_CHARGING


def test_passable_channels():
    wmap = _build_map()
    # 主通道区域应为可通行
    assert wmap.grid[5, 10] == MAP_PASSABLE
    assert wmap.grid[5, 30] == MAP_PASSABLE


def test_storage_cells():
    wmap = _build_map()
    storage_count = int((wmap.grid == MAP_STORAGE).sum())
    assert storage_count > 0
    assert len(wmap.storage_list) == 540  # 9区域×5行×12储位


def test_storage_names_format():
    wmap = _build_map()
    for sname in wmap.storage_list[:10]:
        parts = sname.split("_")
        assert len(parts) == 3, f"Storage name '{sname}' not in Zone_Rn_Bn format"
        assert parts[1].startswith("R")
        assert parts[2].startswith("B")


def test_zone_pos_all_in_grid():
    wmap = _build_map()
    gs = wmap.config.grid_size
    for name, (x, y) in wmap.zone_pos.items():
        assert 0 <= x < gs and 0 <= y < gs, f"{name} at ({x},{y}) out of bounds"


def test_is_passable_bidirectional():
    """全双向：所有可通行格子不检查方向"""
    wmap = _build_map()
    # 在通道上，任何方向都可通行
    x, y = 10, 5  # 主通道位置
    assert wmap.is_passable(x, y)
    assert wmap.is_passable(x, y)


def test_is_passable_obstacle():
    wmap = _build_map()
    assert not wmap.is_passable(-1, 0)
    assert not wmap.is_passable(0, -1)
    assert not wmap.is_passable(100, 0)


def test_is_passable_port():
    wmap = _build_map()
    for name, pcfg in wmap.config.ports.items():
        px, py = pcfg["pos"]
        assert wmap.is_passable(px, py), f"Port {name} not passable"


def test_is_passable_charging():
    wmap = _build_map()
    for cx, cy in wmap.config.charging_points:
        assert wmap.is_passable(cx, cy), f"Charging ({cx},{cy}) not passable"
