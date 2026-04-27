# tests/warehouse/test_inventory.py
from src.warehouse.maps.base import MapRegistry
from src.warehouse.wms.inventory import InventoryManager

import src.warehouse.maps.medium_50x50  # noqa: F401


def test_inventory_init():
    cfg = MapRegistry.get("medium_50x50")
    inv = InventoryManager(cfg)
    status = inv.get_status()
    assert len(status) > 0  # 48 storages


def test_query_by_model():
    cfg = MapRegistry.get("medium_50x50")
    inv = InventoryManager(cfg)
    # 查询第一个model
    all_models = list(inv._items.keys())
    if all_models:
        item = inv.query_by_model(all_models[0])
        assert item is not None


def test_allocate_stock():
    cfg = MapRegistry.get("medium_50x50")
    inv = InventoryManager(cfg)
    all_models = list(inv._items.keys())
    if all_models:
        model = all_models[0]
        item = inv.query_by_model(model)
        if item and item.quantity > 0:
            loc = inv.allocate_stock(model, 1)
            assert loc != ""
            assert inv.query_by_model(model).quantity == item.quantity - 1


def test_receive_stock():
    cfg = MapRegistry.get("medium_50x50")
    inv = InventoryManager(cfg)
    all_models = list(inv._items.keys())
    if all_models:
        model = all_models[0]
        item = inv.query_by_model(model)
        old_qty = item.quantity
        inv.receive_stock(model, 5)
        assert inv.query_by_model(model).quantity == old_qty + 5
