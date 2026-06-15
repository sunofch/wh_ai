"""工业级加固测试：限流器、溯源 API 端点。"""
import pytest
from fastapi.testclient import TestClient

from src.api.app import _SlidingWindowLimiter, create_app
from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401
from src.warehouse.wms.inventory_db import StockManager


class TestSlidingWindowLimiter:
    def test_allows_under_limit(self):
        limiter = _SlidingWindowLimiter(limit=3, window=60)
        assert all(limiter.allow("ip1", now=float(i)) for i in range(3))

    def test_blocks_over_limit(self):
        limiter = _SlidingWindowLimiter(limit=2, window=60)
        limiter.allow("ip1", now=0.0)
        limiter.allow("ip1", now=1.0)
        assert limiter.allow("ip1", now=2.0) is False

    def test_window_expiry_releases(self):
        limiter = _SlidingWindowLimiter(limit=1, window=60)
        limiter.allow("ip1", now=0.0)
        assert limiter.allow("ip1", now=61.0) is True

    def test_keys_isolated(self):
        limiter = _SlidingWindowLimiter(limit=1, window=60)
        limiter.allow("ip1", now=0.0)
        assert limiter.allow("ip2", now=0.0) is True


class TestTraceEndpoint:
    @pytest.fixture
    def client(self, tmp_path):
        mgr = StockManager(db_path=str(tmp_path / "t.db"))
        mgr.seed_from_map(MapRegistry.get("medium_57x47"), seed=42)
        app = create_app(inv_db=mgr)
        with TestClient(app) as c:
            yield c, mgr

    def test_trace_found(self, client):
        c, mgr = client
        model = next(it.model for it in mgr.list_items() if it.available >= 1)
        mgr.receive(model, 1)
        resp = c.get(f"/trace/{model}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["chain_verified"] is True
        assert body["records"]

    def test_trace_not_found(self, client):
        c, _ = client
        assert c.get("/trace/NO-SUCH-MODEL").status_code == 404
