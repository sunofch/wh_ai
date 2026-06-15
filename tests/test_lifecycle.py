"""备件全生命周期（入库→使用→报废）与寿命到期预警测试。

对应 pj4 子课题 4.3：全生命周期数据追踪 + 使用期限到期自动预警。
"""
import sqlite3
from datetime import date, timedelta

import pytest

from src.optimization.warning import classify_life_risk, weeks_until_expiry
from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401
from src.warehouse.wms.inventory_db import StockManager


@pytest.fixture
def mgr(tmp_path):
    path = str(tmp_path / "test.db")
    mgr = StockManager(db_path=path)
    mgr.seed_from_map(MapRegistry.get("medium_57x47"), seed=42)
    return mgr


def _find_model(mgr, min_available: int = 2) -> str:
    from src.warehouse.wms.inventory_db import _PARTS_CATALOG
    mc = MapRegistry.get("medium_57x47")
    for zn, zc in mc.rack_zones.items():
        for part in _PARTS_CATALOG.get(zc.zone_type, []):
            model = f"{part['model_base']}-{zn}"
            item = mgr.query(model)
            if item and item.available >= min_available:
                return model
    raise AssertionError("seed 库存中找不到可用 model")


# ── 字段与迁移 ──

class TestSchema:
    def test_new_db_has_lifecycle_columns(self, mgr):
        model = _find_model(mgr)
        item = mgr.query(model)
        assert item.inbound_date != ""          # seed 时写入
        assert item.expected_life_weeks > 0      # seed 按类目默认寿命
        assert item.scrap_date == ""

    def test_legacy_db_is_migrated(self, tmp_path):
        """旧库（无生命周期字段）打开后自动 ALTER 迁移，不丢数据。"""
        path = str(tmp_path / "legacy.db")
        conn = sqlite3.connect(path)
        conn.execute("""
            CREATE TABLE stock_quant (
                model TEXT PRIMARY KEY, part_name TEXT NOT NULL,
                en_name TEXT DEFAULT '', zone TEXT NOT NULL,
                zone_type TEXT NOT NULL, location TEXT NOT NULL UNIQUE,
                quantity INTEGER NOT NULL DEFAULT 0,
                reserved INTEGER NOT NULL DEFAULT 0,
                max_capacity INTEGER NOT NULL DEFAULT 4,
                updated_at TEXT DEFAULT (datetime('now')),
                CHECK (quantity >= reserved)
            )""")
        conn.execute("""
            CREATE TABLE stock_move (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                move_type TEXT NOT NULL, model TEXT NOT NULL,
                quantity INTEGER NOT NULL, location TEXT NOT NULL,
                order_id TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )""")
        conn.execute(
            "INSERT INTO stock_quant (model, part_name, zone, zone_type, location, quantity)"
            " VALUES ('M1', '轴承', 'Z1', 'mechanical', 'Z1_R1_B1', 5)"
        )
        conn.commit()
        conn.close()

        mgr = StockManager(db_path=path)
        item = mgr.query("M1")
        assert item is not None
        assert item.quantity == 5
        assert item.scrap_date == ""        # 迁移补列默认空
        # 迁移后核心操作可用
        assert mgr.receive("M1", 2) != ""


# ── 入库 / 报废流程 ──

class TestLifecycleFlow:
    def test_receive_updates_inbound_date(self, mgr):
        model = _find_model(mgr)
        mgr.receive(model, 3)
        item = mgr.query(model)
        assert item.inbound_date.startswith(str(date.today().year))

    def test_scrap_reduces_quantity_and_records_move(self, mgr):
        model = _find_model(mgr, min_available=2)
        before = mgr.query(model)
        ok = mgr.scrap(model, 1, reason="寿命到期")
        assert ok
        after = mgr.query(model)
        assert after.quantity == before.quantity - 1
        assert after.scrap_date != ""
        moves = mgr.get_lifecycle(model)
        scraps = [m for m in moves if m["move_type"] == "scrap"]
        assert len(scraps) == 1
        assert scraps[0]["quantity"] == 1
        assert "寿命到期" in scraps[0]["note"]

    def test_scrap_cannot_exceed_available(self, mgr):
        model = _find_model(mgr, min_available=2)
        item = mgr.query(model)
        # 预留后可用减少，报废不能动预留部分
        mgr.reserve(model, item.available - 1, order_id="o1")
        with pytest.raises(ValueError):
            mgr.scrap(model, 2)

    def test_scrap_unknown_model_returns_false(self, mgr):
        assert mgr.scrap("NO-SUCH-MODEL", 1) is False

    def test_set_life_expectancy(self, mgr):
        model = _find_model(mgr)
        mgr.set_life_expectancy(model, 8)
        assert mgr.query(model).expected_life_weeks == 8

    def test_get_lifecycle_returns_full_history(self, mgr):
        model = _find_model(mgr, min_available=2)
        mgr.receive(model, 2)
        loc = mgr.reserve(model, 1, order_id="o-x")
        assert loc != ""
        mgr.confirm(model, 1, order_id="o-x")
        mgr.scrap(model, 1, reason="检验不合格")
        types = [m["move_type"] for m in mgr.get_lifecycle(model)]
        assert types == ["receive", "reserve", "confirm", "scrap"]


# ── 寿命到期预警 ──

class TestLifeRisk:
    def test_expired(self):
        inbound = (date.today() - timedelta(weeks=10)).isoformat()
        assert classify_life_risk(inbound, expected_life_weeks=8) == "expired"

    def test_expiring_within_warn_window(self):
        inbound = (date.today() - timedelta(weeks=7)).isoformat()
        assert classify_life_risk(inbound, expected_life_weeks=8, warn_weeks=2) == "expiring"

    def test_ok(self):
        inbound = (date.today() - timedelta(weeks=1)).isoformat()
        assert classify_life_risk(inbound, expected_life_weeks=52) == "ok"

    def test_unknown_when_missing_data(self):
        assert classify_life_risk("", expected_life_weeks=8) == "unknown"
        assert classify_life_risk("2026-01-01", expected_life_weeks=0) == "unknown"

    def test_weeks_until_expiry(self):
        inbound = (date.today() - timedelta(weeks=3)).isoformat()
        remaining = weeks_until_expiry(inbound, expected_life_weeks=8)
        assert remaining == pytest.approx(5.0, abs=0.2)
        assert weeks_until_expiry("", 8) is None

    def test_list_life_warnings_from_db(self, mgr):
        """库内寿命预警清单：到期/临期备件被列出。"""
        model = _find_model(mgr)
        mgr.set_life_expectancy(model, 1)
        # inbound_date 是 seed 当天，寿命1周 → 处于 expiring 窗口内
        warnings = mgr.list_life_warnings(warn_weeks=2)
        assert any(w["model"] == model for w in warnings)
        assert all(w["life_risk"] in ("expired", "expiring") for w in warnings)
