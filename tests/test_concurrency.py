"""高并发基础设施测试。

对应 pj4 考核指标：高并发场景支持（库存层并发写不丢数据、不报错，
哈希链存证在并发下仍完整）。
"""
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401
from src.warehouse.wms.inventory_db import StockManager


@pytest.fixture
def mgr(tmp_path):
    m = StockManager(db_path=str(tmp_path / "t.db"))
    m.seed_from_map(MapRegistry.get("medium_57x47"), seed=42)
    return m


def _find_model(mgr) -> str:
    for item in mgr.list_items():
        if item.available >= 1:
            return item.model
    raise AssertionError("无可用库存")


class TestConcurrentWrites:
    def test_busy_timeout_configured(self, mgr):
        with mgr._conn() as conn:
            timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert timeout >= 1000  # 毫秒；并发写冲突时等待而非立即失败

    def test_parallel_receive_no_loss(self, mgr):
        """8 线程并发入库，总量准确无丢失。"""
        model = _find_model(mgr)
        before = mgr.query(model).quantity
        n_threads, ops_each = 8, 10

        def worker(_):
            for _ in range(ops_each):
                mgr.receive(model, 1)

        with ThreadPoolExecutor(max_workers=n_threads) as pool:
            list(pool.map(worker, range(n_threads)))

        assert mgr.query(model).quantity == before + n_threads * ops_each

    def test_parallel_reserve_never_oversells(self, mgr):
        """并发预留不超卖：成功预留总量 ≤ 可用库存。"""
        model = _find_model(mgr)
        available = mgr.query(model).available
        results = []

        def worker(i):
            return mgr.reserve(model, 1, order_id=f"c{i}")

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(worker, range(available + 20)))

        succeeded = sum(1 for loc in results if loc)
        assert succeeded == available
        assert mgr.query(model).available == 0

    def test_chain_intact_after_concurrency(self, mgr):
        model = _find_model(mgr)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: mgr.receive(model, 1), range(40)))
        trace = mgr.trace(model)
        assert trace["chain_verified"] is True
        assert len(trace["records"]) == 40


class TestBenchmarkScript:
    def test_benchmark_runs_and_reports_tps(self, tmp_path):
        from scripts.benchmark_tps import run_stock_benchmark

        report = run_stock_benchmark(
            db_path=str(tmp_path / "bench.db"), n_threads=4, ops_per_thread=25
        )
        assert report["total_ops"] == 100
        assert report["tps"] > 0
        assert report["errors"] == 0
