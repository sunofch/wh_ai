# src/warehouse/wms/inventory_db.py
"""SQLite 持久化库存管理（WAL模式，支持高并发读写）"""
from __future__ import annotations
import random
import sqlite3
from contextlib import contextmanager

from src.warehouse.models import InventoryItem, MapConfig


class InventoryDB:
    def __init__(self, db_path: str = "data/inventory.db"):
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    model        TEXT PRIMARY KEY,
                    part_name    TEXT NOT NULL,
                    zone         TEXT NOT NULL,
                    zone_type    TEXT NOT NULL,
                    location     TEXT NOT NULL UNIQUE,
                    quantity     INTEGER NOT NULL DEFAULT 0,
                    max_capacity INTEGER NOT NULL DEFAULT 4
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_part_name ON inventory(part_name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_zone_type ON inventory(zone_type)"
            )

    def seed_from_map(self, map_config: MapConfig, seed: int = 42):
        """首次启动时从地图配置初始化库存，已存在的记录跳过。"""
        rng = random.Random(seed)
        part_names = {
            "mechanical": ["轴承", "齿轮", "液压泵", "联轴器", "制动器"],
            "electrical": ["电机", "传感器", "电缆", "控制器", "继电器"],
            "consumable": ["密封件", "润滑油", "滤芯", "阀门", "油管"],
            "safety": ["安全帽", "手套", "护目镜", "安全带", "防护服"],
            "tool": ["扳手", "万用表", "电钻", "螺丝刀", "钳子"],
        }
        idx = 0
        with self._conn() as conn:
            for zone_name, zone_cfg in map_config.rack_zones.items():
                zone_type = zone_cfg.zone_type
                parts = part_names.get(zone_type, ["备件"])
                num_rows = min(zone_cfg.height // 2, 5)
                bays_per_row = 12
                for row in range(1, num_rows + 1):
                    for bay in range(1, bays_per_row + 1):
                        location = f"{zone_name}_R{row}_B{bay}"
                        qty = rng.randint(0, 3)
                        model = f"M{idx + 100}"      # 全局唯一型号，M100 起始
                        part_name = parts[idx % len(parts)]
                        conn.execute(
                            """INSERT OR IGNORE INTO inventory
                               (model, part_name, zone, zone_type, location, quantity)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (model, part_name, zone_name, zone_type, location, qty),
                        )
                        idx += 1

    def query_by_model(self, model: str) -> InventoryItem | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM inventory WHERE model = ?", (model,)
            ).fetchone()
        return self._row_to_item(row) if row else None

    def query_by_part_name(self, part_name: str) -> InventoryItem | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM inventory WHERE part_name LIKE ? LIMIT 1",
                (f"%{part_name}%",),
            ).fetchone()
        return self._row_to_item(row) if row else None

    def allocate_stock(self, model: str, quantity: int) -> str:
        """扣减库存，成功返回储位名，库存不足返回空字符串。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT location, quantity FROM inventory WHERE model = ?",
                (model,),
            ).fetchone()
            if row is None or row["quantity"] < quantity:
                return ""
            conn.execute(
                "UPDATE inventory SET quantity = quantity - ? WHERE model = ?",
                (quantity, model),
            )
            return row["location"]

    def receive_stock(self, model: str, quantity: int) -> str:
        """入库，返回储位名。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT location FROM inventory WHERE model = ?", (model,)
            ).fetchone()
            if row is None:
                return ""
            conn.execute(
                "UPDATE inventory SET quantity = quantity + ? WHERE model = ?",
                (quantity, model),
            )
            return row["location"]

    def get_status(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT location, quantity FROM inventory"
            ).fetchall()
        return {row["location"]: row["quantity"] for row in rows}

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> InventoryItem:
        return InventoryItem(
            model=row["model"],
            part_name=row["part_name"],
            quantity=row["quantity"],
            location=row["location"],
            zone=row["zone"],
            max_capacity=row["max_capacity"],
        )
