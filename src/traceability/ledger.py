"""哈希链账本：备件流转数据上链存证。

每个区块固化一条业务事件（stock_move），block_hash 链式依赖前块，
任何历史篡改都会使后续校验断链。与业务库同一个 SQLite 事务写入，
保证存证与业务数据原子一致。

真实联盟链（Hyperledger Fabric / FISCO BCOS）替换路径见 adapters.py。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

GENESIS_HASH = "0" * 64


def _canonical(payload: dict) -> str:
    """payload 的规范化 JSON 序列化（键排序，保证哈希确定性）。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _block_hash(idx: int, ts: str, payload_hash: str, prev_hash: str) -> str:
    return _sha256(f"{idx}|{ts}|{payload_hash}|{prev_hash}")


class HashChainLedger:
    """在给定 SQLite 连接上维护 ledger_block 哈希链。

    连接的事务边界由调用方控制：与业务写操作放在同一事务中调用
    append() 即可获得原子的"业务+存证"写入。
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @staticmethod
    def init_schema(conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ledger_block (
                idx          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           TEXT NOT NULL,
                payload      TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                prev_hash    TEXT NOT NULL,
                block_hash   TEXT NOT NULL UNIQUE,
                model        TEXT NOT NULL DEFAULT '',
                order_id     TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lb_model ON ledger_block(model)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lb_order ON ledger_block(order_id)"
        )

    def _tip(self) -> tuple[int, str]:
        """返回 (链高, 链尾哈希)；空链返回 (0, GENESIS_HASH)。"""
        row = self._conn.execute(
            "SELECT idx, block_hash FROM ledger_block ORDER BY idx DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return 0, GENESIS_HASH
        return row["idx"], row["block_hash"]

    def append(self, payload: dict, model: str = "", order_id: str = "") -> dict:
        """追加一个区块并返回区块字典。"""
        tip_idx, prev_hash = self._tip()
        idx = tip_idx + 1
        ts = datetime.now(timezone.utc).isoformat()
        text = _canonical(payload)
        payload_hash = _sha256(text)
        block_hash = _block_hash(idx, ts, payload_hash, prev_hash)
        self._conn.execute(
            "INSERT INTO ledger_block "
            "(idx, ts, payload, payload_hash, prev_hash, block_hash, model, order_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (idx, ts, text, payload_hash, prev_hash, block_hash, model, order_id),
        )
        return {
            "idx": idx,
            "ts": ts,
            "payload": payload,
            "payload_hash": payload_hash,
            "prev_hash": prev_hash,
            "block_hash": block_hash,
        }

    def verify(self) -> tuple[bool, int | None]:
        """全链校验。返回 (是否完整, 首个被篡改区块的 idx 或 None)。"""
        prev_hash = GENESIS_HASH
        rows = self._conn.execute(
            "SELECT idx, ts, payload, payload_hash, prev_hash, block_hash "
            "FROM ledger_block ORDER BY idx"
        )
        for row in rows:
            payload_ok = _sha256(row["payload"]) == row["payload_hash"]
            link_ok = row["prev_hash"] == prev_hash
            hash_ok = _block_hash(
                row["idx"], row["ts"], row["payload_hash"], row["prev_hash"]
            ) == row["block_hash"]
            if not (payload_ok and link_ok and hash_ok):
                return False, row["idx"]
            prev_hash = row["block_hash"]
        return True, None

    def query_model(self, model: str) -> list[dict]:
        """按型号检索上链记录（带索引，满足 <2s 溯源查询指标）。"""
        rows = self._conn.execute(
            "SELECT idx, ts, payload, payload_hash, prev_hash, block_hash "
            "FROM ledger_block WHERE model = ? ORDER BY idx",
            (model,),
        ).fetchall()
        return [
            {
                "idx": row["idx"],
                "ts": row["ts"],
                "payload": json.loads(row["payload"]),
                "payload_hash": row["payload_hash"],
                "prev_hash": row["prev_hash"],
                "block_hash": row["block_hash"],
            }
            for row in rows
        ]
