import pytest
from src.warehouse.wms.inventory_db import InventoryDB
from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    db = InventoryDB(db_path=path)
    map_config = MapRegistry.get("medium_57x47")
    db.seed_from_map(map_config, seed=42)
    return db


def test_seed_creates_records(db):
    status = db.get_status()
    assert len(status) > 0


def test_query_by_model_returns_item(db):
    item = db.query_by_model("M100")
    assert item is not None
    assert item.model == "M100"
    assert item.location != ""


def test_query_by_part_name_fuzzy(db):
    item = db.query_by_part_name("轴承")
    assert item is not None
    assert "轴承" in item.part_name


def test_allocate_stock_deducts(db):
    item = db.query_by_part_name("轴承")
    initial_qty = item.quantity
    if initial_qty >= 2:
        location = db.allocate_stock(item.model, 2)
        assert location == item.location
        updated = db.query_by_model(item.model)
        assert updated.quantity == initial_qty - 2


def test_allocate_stock_insufficient_returns_empty(db):
    item = db.query_by_part_name("轴承")
    result = db.allocate_stock(item.model, 9999)
    assert result == ""


def test_receive_stock_adds(db):
    item = db.query_by_part_name("齿轮")
    initial_qty = item.quantity
    db.receive_stock(item.model, 3)
    updated = db.query_by_model(item.model)
    assert updated.quantity == initial_qty + 3


def test_seed_idempotent(db):
    map_config = MapRegistry.get("medium_57x47")
    db.seed_from_map(map_config, seed=42)
    status = db.get_status()
    count = len(status)
    db.seed_from_map(map_config, seed=42)
    assert len(db.get_status()) == count
