"""轻量级区块链溯源测试。

对应 pj4 子课题 4.3：备件入库→报废全生命周期数据上链存证，
溯源查询响应 < 2 秒；哈希链 + 默克尔证明，预留联盟链适配层。
"""
import sqlite3
import time

import pytest

from src.traceability.ledger import HashChainLedger
from src.traceability.merkle import merkle_proof, merkle_root, verify_proof
from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401
from src.warehouse.wms.inventory_db import StockManager


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    HashChainLedger.init_schema(c)
    yield c
    c.close()


@pytest.fixture
def mgr(tmp_path):
    m = StockManager(db_path=str(tmp_path / "t.db"))
    m.seed_from_map(MapRegistry.get("medium_57x47"), seed=42)
    return m


def _find_model(mgr, min_available: int = 2) -> str:
    for item in mgr.list_items():
        if item.available >= min_available:
            return item.model
    raise AssertionError("无可用库存")


# ── 哈希链 ──

class TestHashChain:
    def test_append_links_blocks(self, conn):
        ledger = HashChainLedger(conn)
        b1 = ledger.append({"move": "receive", "qty": 2}, model="M1")
        b2 = ledger.append({"move": "confirm", "qty": 1}, model="M1")
        assert b2["prev_hash"] == b1["block_hash"]
        assert b1["idx"] + 1 == b2["idx"]

    def test_verify_ok(self, conn):
        ledger = HashChainLedger(conn)
        for i in range(5):
            ledger.append({"i": i}, model="M1")
        ok, bad_idx = ledger.verify()
        assert ok and bad_idx is None

    def test_tamper_detected(self, conn):
        ledger = HashChainLedger(conn)
        for i in range(5):
            ledger.append({"i": i}, model="M1")
        conn.execute("UPDATE ledger_block SET payload = '{\"i\": 999}' WHERE idx = 3")
        ok, bad_idx = ledger.verify()
        assert not ok
        assert bad_idx == 3

    def test_query_by_model(self, conn):
        ledger = HashChainLedger(conn)
        ledger.append({"a": 1}, model="M1")
        ledger.append({"b": 2}, model="M2")
        ledger.append({"c": 3}, model="M1")
        records = ledger.query_model("M1")
        assert len(records) == 2


# ── 默克尔证明 ──

class TestMerkle:
    def test_root_deterministic(self):
        hashes = [f"{i:064x}" for i in range(7)]
        assert merkle_root(hashes) == merkle_root(hashes)

    def test_proof_verifies(self):
        hashes = [f"{i:064x}" for i in range(6)]
        root = merkle_root(hashes)
        for idx, leaf in enumerate(hashes):
            proof = merkle_proof(hashes, idx)
            assert verify_proof(leaf, proof, root)

    def test_wrong_leaf_fails(self):
        hashes = [f"{i:064x}" for i in range(4)]
        root = merkle_root(hashes)
        proof = merkle_proof(hashes, 0)
        assert not verify_proof("f" * 64, proof, root)

    def test_single_leaf(self):
        h = "a" * 64
        assert merkle_root([h]) == h
        assert verify_proof(h, merkle_proof([h], 0), h)


# ── 库存操作自动上链 ──

class TestStockLedgerIntegration:
    def test_moves_are_recorded_on_chain(self, mgr):
        model = _find_model(mgr)
        mgr.receive(model, 2)
        mgr.reserve(model, 1, order_id="o1")
        mgr.confirm(model, 1, order_id="o1")
        mgr.scrap(model, 1, reason="到期")

        trace = mgr.trace(model)
        types = [r["payload"]["move_type"] for r in trace["records"]]
        assert types == ["receive", "reserve", "confirm", "scrap"]
        assert trace["chain_verified"] is True

    def test_trace_query_under_2_seconds(self, mgr):
        model = _find_model(mgr)
        for _ in range(20):
            mgr.receive(model, 1)
        start = time.perf_counter()
        trace = mgr.trace(model)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0
        assert trace["elapsed_ms"] < 2000
        assert len(trace["records"]) == 20

    def test_trace_unknown_model_empty(self, mgr):
        trace = mgr.trace("NO-SUCH-MODEL")
        assert trace["records"] == []
        assert trace["chain_verified"] is True
