import pytest
from src.warehouse.wms.inventory_db import StockManager
from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401


@pytest.fixture
def mgr(tmp_path):
    path = str(tmp_path / "test.db")
    mgr = StockManager(db_path=path)
    map_config = MapRegistry.get("medium_57x47")
    mgr.seed_from_map(map_config, seed=42)
    return mgr


def _find_model(mgr):
    """辅助：获取一个有库存的 model"""
    from src.warehouse.maps.base import MapRegistry
    import src.warehouse.maps.medium_57x47  # noqa: F401
    mc = MapRegistry.get("medium_57x47")
    from src.warehouse.wms.inventory_db import _PARTS_CATALOG
    for zn, zc in mc.rack_zones.items():
        for part in _PARTS_CATALOG.get(zc.zone_type, []):
            model = f"{part['model_base']}-{zn}"
            item = mgr.query(model)
            if item and item.available > 0:
                return model
    return None


# ── seed & query ──

def test_seed_creates_records(mgr):
    status = mgr.get_status()
    assert len(status) > 0


def test_query_by_model(mgr):
    model = _find_model(mgr)
    assert model is not None
    item = mgr.query(model)
    assert item is not None
    assert item.model == model
    assert item.available == item.quantity - item.reserved


def test_query_by_name_fuzzy(mgr):
    item = mgr.query_by_name("轴承")
    assert item is not None
    assert "轴承" in item.part_name


def test_seed_idempotent(mgr):
    from src.warehouse.maps.base import MapRegistry
    import src.warehouse.maps.medium_57x47  # noqa: F401
    mc = MapRegistry.get("medium_57x47")
    count = len(mgr.get_status())
    mgr.seed_from_map(mc, seed=42)
    assert len(mgr.get_status()) == count


# ── reserve / confirm / release 三阶段 ──

def test_reserve_locks_stock(mgr):
    model = _find_model(mgr)
    item = mgr.query(model)
    initial_qty = item.quantity
    initial_reserved = item.reserved

    location = mgr.reserve(model, 2, order_id="ord-1")
    assert location != ""

    updated = mgr.query(model)
    assert updated.reserved == initial_reserved + 2
    assert updated.quantity == initial_qty        # quantity 不变
    assert updated.available == initial_qty - initial_reserved - 2


def test_reserve_insufficient_returns_empty(mgr):
    model = _find_model(mgr)
    item = mgr.query(model)
    result = mgr.reserve(model, item.available + 999)
    assert result == ""


def test_confirm_deducts_quantity_and_reserved(mgr):
    model = _find_model(mgr)
    item = mgr.query(model)
    initial_qty = item.quantity

    mgr.reserve(model, 2, order_id="ord-2")
    mgr.confirm(model, 2, order_id="ord-2")

    updated = mgr.query(model)
    assert updated.quantity == initial_qty - 2
    assert updated.reserved == item.reserved      # reserved 回到原值
    assert updated.available == updated.quantity - updated.reserved


def test_release_restores_available(mgr):
    model = _find_model(mgr)
    item = mgr.query(model)
    initial_qty = item.quantity

    mgr.reserve(model, 2, order_id="ord-3")
    mgr.release(model, 2, order_id="ord-3")

    updated = mgr.query(model)
    assert updated.quantity == initial_qty        # quantity 不变
    assert updated.reserved == item.reserved      # reserved 回到原值


def test_reserve_then_reserve_again(mgr):
    model = _find_model(mgr)
    item = mgr.query(model)
    total = item.available

    loc1 = mgr.reserve(model, 1, order_id="ord-a")
    loc2 = mgr.reserve(model, 1, order_id="ord-b")
    assert loc1 != ""
    assert loc2 != ""

    updated = mgr.query(model)
    assert updated.reserved == item.reserved + 2
    assert updated.available == total - 2


# ── receive ──

def test_receive_adds_quantity(mgr):
    model = _find_model(mgr)
    item = mgr.query(model)
    initial_qty = item.quantity

    mgr.receive(model, 3)
    updated = mgr.query(model)
    assert updated.quantity == initial_qty + 3


# ── stock_move 审计 ──

def test_move_audit_trail(mgr):
    model = _find_model(mgr)
    mgr.reserve(model, 1, order_id="ord-x")
    mgr.confirm(model, 1, order_id="ord-x")

    with mgr._conn() as conn:
        moves = conn.execute(
            "SELECT move_type FROM stock_move WHERE order_id = 'ord-x' ORDER BY id"
        ).fetchall()
    types = [r["move_type"] for r in moves]
    assert types == ["reserve", "confirm"]


def test_move_audit_release(mgr):
    model = _find_model(mgr)
    mgr.reserve(model, 1, order_id="ord-y")
    mgr.release(model, 1, order_id="ord-y")

    with mgr._conn() as conn:
        moves = conn.execute(
            "SELECT move_type FROM stock_move WHERE order_id = 'ord-y' ORDER BY id"
        ).fetchall()
    types = [r["move_type"] for r in moves]
    assert types == ["reserve", "release"]
