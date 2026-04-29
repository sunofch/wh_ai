# tests/warehouse/test_map_builder.py
"""地图构建器测试 — 行列式货架、巷道、子通道、方向感知"""

import numpy as np
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import (
    WarehouseMap, MAP_PASSABLE, MAP_PORT, MAP_CHARGING,
    MAP_STORAGE, MAP_AISLE_DOWN, MAP_AISLE_UP, MAP_SUB_AISLE,
)
import src.warehouse.maps.medium_50x50


def _build_map() -> WarehouseMap:
    cfg = MapRegistry.get("medium_50x50")
    return WarehouseMap(cfg)


def test_storage_count():
    wmap = _build_map()
    assert len(wmap.storage_list) == 450  # 9 zones × 5 rows × 10 bays


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


def test_main_channels_passable():
    wmap = _build_map()
    # Horizontal channel at y=6
    assert wmap.grid[6, 9] == MAP_PASSABLE
    # Vertical channel at x=17
    assert wmap.grid[10, 17] == MAP_PASSABLE


def test_aisle_direction_cells():
    wmap = _build_map()
    down_count = int((wmap.grid == MAP_AISLE_DOWN).sum())
    up_count = int((wmap.grid == MAP_AISLE_UP).sum())
    assert down_count > 0, "No AISLE_DOWN cells found"
    assert up_count > 0, "No AISLE_UP cells found"


def test_sub_aisle_cells():
    wmap = _build_map()
    sub_count = int((wmap.grid == MAP_SUB_AISLE).sum())
    assert sub_count > 0, "No SUB_AISLE cells found"


def test_storage_cells():
    wmap = _build_map()
    # sub_aisle_cols positions are overwritten to SUB_AISLE
    # 9 zones × 5 rows × 10 bays = 450 names, but 4 sub_aisle cols × 5 rows × 9 zones = 180 are SUB_AISLE
    storage_count = int((wmap.grid == MAP_STORAGE).sum())
    sub_count = int((wmap.grid == MAP_SUB_AISLE).sum())
    assert storage_count + sub_count > 0
    assert len(wmap.storage_list) == 450


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


def test_is_passable_aisle_down():
    wmap = _build_map()
    positions = np.argwhere(wmap.grid == MAP_AISLE_DOWN)
    assert len(positions) > 0
    y, x = positions[0]
    # dy=1 (moving down) should be allowed
    assert wmap.is_passable(int(x), int(y), dx=0, dy=1)
    # dy=-1 (moving up) should be blocked
    assert not wmap.is_passable(int(x), int(y), dx=0, dy=-1)


def test_is_passable_aisle_up():
    wmap = _build_map()
    positions = np.argwhere(wmap.grid == MAP_AISLE_UP)
    assert len(positions) > 0
    y, x = positions[0]
    # dy=-1 (moving up) should be allowed
    assert wmap.is_passable(int(x), int(y), dx=0, dy=-1)
    # dy=1 (moving down) should be blocked
    assert not wmap.is_passable(int(x), int(y), dx=0, dy=1)


def test_is_passable_aisle_lateral():
    """AGV can move laterally in aisle to enter/exit sub-aisle"""
    wmap = _build_map()
    positions = np.argwhere(wmap.grid == MAP_AISLE_DOWN)
    y, x = positions[0]
    # dx!=0 (lateral) should be allowed
    assert wmap.is_passable(int(x), int(y), dx=1, dy=0)
    assert wmap.is_passable(int(x), int(y), dx=-1, dy=0)


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


def test_aisle_info_populated():
    wmap = _build_map()
    assert len(wmap.aisle_info) > 0
    for aid, acfg in wmap.aisle_info.items():
        assert acfg.direction in ("down", "up")
