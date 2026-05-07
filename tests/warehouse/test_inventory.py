# tests/warehouse/test_inventory.py
"""库存管理测试 — rack_zones 储位命名"""

from src.warehouse.maps.base import MapRegistry
from src.warehouse.wms.inventory import InventoryManager
import src.warehouse.maps.medium_57x47


def _make_inv():
    cfg = MapRegistry.get("medium_57x47")
    return InventoryManager(cfg)


def test_inventory_storage_count():
    inv = _make_inv()
    assert len(inv.get_storage_names()) == 540


def test_inventory_zone_names():
    inv = _make_inv()
    zones = inv.get_all_zone_names()
    assert len(zones) == 9
    assert "Mech1" in zones
    assert "Cons3" in zones


def test_inventory_storage_name_format():
    inv = _make_inv()
    for sname in inv.get_storage_names():
        parts = sname.split("_")
        assert len(parts) == 3
        assert parts[1].startswith("R")
        assert parts[2].startswith("B")


def test_inventory_status():
    inv = _make_inv()
    status = inv.get_status()
    assert len(status) == 540
    for qty in status.values():
        assert 0 <= qty <= 3


def test_inventory_query_by_model():
    inv = _make_inv()
    for model, item in inv._items.items():
        found = inv.query_by_model(model)
        assert found is not None
        assert found.model == model


def test_inventory_allocate():
    inv = _make_inv()
    # Try allocating from first model
    models = list(inv._items.keys())
    if models:
        loc = inv.allocate_stock(models[0], 1)
        assert isinstance(loc, str)
