# src/warehouse/wms/inventory_db.py
"""SQLite 持久化库存管理（WAL模式，双表：stock_quant + stock_move）

stock_quant 同时承载备件生命周期元数据（入库日期 / 预期寿命 / 报废日期），
stock_move 记录 receive/reserve/confirm/release/scrap 全流程履历，
支撑 pj4 子课题 4.3 的全生命周期追踪与寿命到期预警。
"""
from __future__ import annotations
import random
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone

from src.optimization.warning import classify_life_risk
from src.traceability.ledger import HashChainLedger
from src.warehouse.models import InventoryItem, MapConfig

# 按区域类型给出的默认预期寿命（周），seed 时写入，可通过 set_life_expectancy 调整
_DEFAULT_LIFE_WEEKS: dict[str, int] = {
    "mechanical": 104,
    "electrical": 156,
    "consumable": 26,
    "safety": 52,
    "tool": 208,
}

# 预定义工业备件目录，按区域类型分类
# model_base 加 "-{zone_name}" 后缀保证全局唯一
_PARTS_CATALOG: dict[str, list[dict]] = {
    "mechanical": [
        {"part_name": "深沟球轴承",   "en_name": "Deep Groove Ball Bearing",    "model_base": "6208-2RS-C3-SKF"},
        {"part_name": "斜齿圆柱齿轮", "en_name": "Helical Cylindrical Gear",    "model_base": "HCG-M3-40T-S45C"},
        {"part_name": "齿轮油泵",     "en_name": "Gear Oil Pump",               "model_base": "CBN-E314-ALR-BOSCH"},
        {"part_name": "弹性爪型联轴器","en_name": "Flexible Jaw Coupling",       "model_base": "ROTEX-48-98ShA-KTR"},
        {"part_name": "液压盘式制动器","en_name": "Hydraulic Disc Brake",        "model_base": "HDB-300-12BAR-SIME"},
    ],
    "electrical": [
        {"part_name": "三相异步电动机",   "en_name": "Three Phase Induction Motor",      "model_base": "Y160M-4-11kW-ABB"},
        {"part_name": "漫反射光电传感器", "en_name": "Diffuse Photoelectric Sensor",     "model_base": "E3Z-D61-2M-OMRON"},
        {"part_name": "变频调速器",       "en_name": "Variable Frequency Drive",         "model_base": "ACS580-039A-ABB"},
        {"part_name": "可编程逻辑控制器", "en_name": "Programmable Logic Controller",    "model_base": "CPU1214C-DC-SIEM"},
        {"part_name": "中间继电器",       "en_name": "Intermediate Relay",               "model_base": "MY4N-J-24VDC-OMRON"},
    ],
    "consumable": [
        {"part_name": "骨架旋转油封",   "en_name": "Shaft Rotary Oil Seal",            "model_base": "TC-50x70x10-NBR-NOK"},
        {"part_name": "抗磨液压油",     "en_name": "Anti-Wear Hydraulic Oil",          "model_base": "L-HM46-200L-KUNLUN"},
        {"part_name": "高压液压油滤芯", "en_name": "High Pressure Hydraulic Filter",   "model_base": "HF-250x20Q-HYDAC"},
        {"part_name": "电磁截止阀",     "en_name": "Electromagnetic Shut-off Valve",   "model_base": "YCFC-25-DN25-24V"},
        {"part_name": "高压橡胶软管",   "en_name": "High Pressure Rubber Hose",        "model_base": "HPH-DN12-1200-315bar"},
    ],
    "safety": [
        {"part_name": "ABS工程安全帽",  "en_name": "ABS Engineering Safety Helmet",    "model_base": "VGard-E2-WHT-MSA"},
        {"part_name": "高压绝缘手套",   "en_name": "High Voltage Insulation Gloves",   "model_base": "IEG-10kV-CL2-HNW"},
        {"part_name": "防冲击护目镜",   "en_name": "Impact Resistant Safety Goggles", "model_base": "VMaxx-OTG-CLR-UVEX"},
        {"part_name": "全身式安全带",   "en_name": "Full Body Safety Harness",         "model_base": "ExofitNXT-1113917-3M"},
        {"part_name": "B类防化防护服",  "en_name": "Type B Chemical Protective Suit",  "model_base": "Tychem-4510-BLU-DP"},
    ],
    "tool": [
        {"part_name": "液压力矩扳手",   "en_name": "Hydraulic Torque Wrench",          "model_base": "HTW-3400Nm-ENERPAC"},
        {"part_name": "数字钳形万用表", "en_name": "Digital Clamp Multimeter",         "model_base": "F325-600V-FLUKE"},
        {"part_name": "充电冲击电钻",   "en_name": "Cordless Hammer Impact Drill",     "model_base": "DHP481Z-18V-MAKITA"},
        {"part_name": "内六角扳手组套", "en_name": "Hex Key Wrench Set",               "model_base": "96T-208mm-WIHA"},
        {"part_name": "液压压线钳",     "en_name": "Hydraulic Cable Crimping Pliers",  "model_base": "YQC-300A-BURNDY"},
    ],
}


class StockManager:
    def __init__(self, db_path: str = "data/inventory.db"):
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        # 并发写冲突时等待重试而非立即 SQLITE_BUSY 失败
        conn.execute("PRAGMA busy_timeout=5000")
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
                CREATE TABLE IF NOT EXISTS stock_quant (
                    model        TEXT PRIMARY KEY,
                    part_name    TEXT NOT NULL,
                    en_name      TEXT DEFAULT '',
                    zone         TEXT NOT NULL,
                    zone_type    TEXT NOT NULL,
                    location     TEXT NOT NULL UNIQUE,
                    quantity     INTEGER NOT NULL DEFAULT 0,
                    reserved     INTEGER NOT NULL DEFAULT 0,
                    max_capacity INTEGER NOT NULL DEFAULT 4,
                    inbound_date TEXT NOT NULL DEFAULT '',
                    expected_life_weeks INTEGER NOT NULL DEFAULT 0,
                    scrap_date   TEXT NOT NULL DEFAULT '',
                    updated_at   TEXT DEFAULT (datetime('now')),
                    CHECK (quantity >= reserved)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sq_part_name ON stock_quant(part_name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sq_en_name ON stock_quant(en_name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sq_zone_type ON stock_quant(zone_type)"
            )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_move (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    move_type  TEXT NOT NULL,
                    model      TEXT NOT NULL,
                    quantity   INTEGER NOT NULL,
                    location   TEXT NOT NULL,
                    order_id   TEXT DEFAULT '',
                    note       TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            self._migrate_columns(conn)
            HashChainLedger.init_schema(conn)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sm_model ON stock_move(model)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sm_order_id ON stock_move(order_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sm_created ON stock_move(created_at)"
            )

    @staticmethod
    def _migrate_columns(conn: sqlite3.Connection) -> None:
        """旧库自动补齐生命周期相关列（ALTER TABLE 幂等迁移）。"""
        migrations = {
            "stock_quant": [
                ("inbound_date", "TEXT NOT NULL DEFAULT ''"),
                ("expected_life_weeks", "INTEGER NOT NULL DEFAULT 0"),
                ("scrap_date", "TEXT NOT NULL DEFAULT ''"),
            ],
            "stock_move": [
                ("note", "TEXT NOT NULL DEFAULT ''"),
            ],
        }
        for table, columns in migrations.items():
            existing = {
                row[1] for row in conn.execute(f"PRAGMA table_info({table})")
            }
            for name, decl in columns:
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    @staticmethod
    def _record_move(
        conn: sqlite3.Connection,
        move_type: str,
        model: str,
        quantity: int,
        location: str,
        order_id: str = "",
        note: str = "",
    ) -> None:
        """写一条库存流水并同事务上链存证（业务与存证原子一致）。"""
        conn.execute(
            "INSERT INTO stock_move (move_type, model, quantity, location, order_id, note) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (move_type, model, quantity, location, order_id, note),
        )
        HashChainLedger(conn).append(
            {
                "move_type": move_type,
                "model": model,
                "quantity": quantity,
                "location": location,
                "order_id": order_id,
                "note": note,
            },
            model=model,
            order_id=order_id,
        )

    def trace(self, model: str) -> dict:
        """全生命周期可信溯源查询：上链记录 + 全链完整性校验 + 耗时。"""
        start = time.perf_counter()
        with self._conn() as conn:
            ledger = HashChainLedger(conn)
            records = ledger.query_model(model)
            verified, bad_idx = ledger.verify()
        return {
            "model": model,
            "records": records,
            "chain_verified": verified,
            "first_invalid_block": bad_idx,
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
        }

    def seed_from_map(self, map_config: MapConfig, seed: int = 42):
        """从地图配置初始化库存，每个区域按预定义工业备件目录填充，已存在的记录跳过。"""
        rng = random.Random(seed)
        with self._conn() as conn:
            for zone_name, zone_cfg in map_config.rack_zones.items():
                zone_type = zone_cfg.zone_type
                catalog = _PARTS_CATALOG.get(zone_type, [])
                if not catalog:
                    continue
                for slot_idx, part in enumerate(catalog):
                    row_num = slot_idx // 5 + 1
                    bay_num = slot_idx % 5 + 1
                    location = f"{zone_name}_R{row_num}_B{bay_num}"
                    model = f"{part['model_base']}-{zone_name}"
                    qty = rng.randint(2, 8)
                    conn.execute(
                        """INSERT OR IGNORE INTO stock_quant
                           (model, part_name, en_name, zone, zone_type, location, quantity,
                            inbound_date, expected_life_weeks)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (model, part["part_name"], part["en_name"],
                         zone_name, zone_type, location, qty,
                         date.today().isoformat(),
                         _DEFAULT_LIFE_WEEKS.get(zone_type, 0)),
                    )

    def reserve(self, model: str, quantity: int, order_id: str = "") -> str:
        """预留库存，返回 location。库存不足返回空字符串。

        条件 UPDATE 原子完成"校验+预留"，并发下不会超卖。
        """
        if quantity <= 0:
            raise ValueError(f"reserve quantity must be positive, got {quantity}")
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE stock_quant SET reserved = reserved + ?, "
                "updated_at = datetime('now') "
                "WHERE model = ? AND quantity - reserved >= ?",
                (quantity, model, quantity),
            )
            if cur.rowcount == 0:
                return ""
            row = conn.execute(
                "SELECT location FROM stock_quant WHERE model = ?", (model,)
            ).fetchone()
            self._record_move(conn, "reserve", model, quantity, row["location"], order_id)
            return row["location"]

    def confirm(self, model: str, quantity: int, order_id: str = "") -> None:
        """确认扣减：quantity 和 reserved 同时减少（条件 UPDATE 原子校验）。"""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE stock_quant SET quantity = quantity - ?, reserved = reserved - ?, "
                "updated_at = datetime('now') WHERE model = ? AND reserved >= ?",
                (quantity, quantity, model, quantity),
            )
            if cur.rowcount == 0:
                row = conn.execute(
                    "SELECT reserved FROM stock_quant WHERE model = ?", (model,)
                ).fetchone()
                if row is None:
                    return
                raise ValueError(
                    f"cannot confirm {quantity} of {model}: only {row['reserved']} reserved"
                )
            row = conn.execute(
                "SELECT location FROM stock_quant WHERE model = ?", (model,)
            ).fetchone()
            self._record_move(conn, "confirm", model, quantity, row["location"], order_id)

    def release(self, model: str, quantity: int, order_id: str = "") -> None:
        """释放预留：reserved 减少（条件 UPDATE 原子校验）。"""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE stock_quant SET reserved = reserved - ?, "
                "updated_at = datetime('now') WHERE model = ? AND reserved >= ?",
                (quantity, model, quantity),
            )
            if cur.rowcount == 0:
                row = conn.execute(
                    "SELECT reserved FROM stock_quant WHERE model = ?", (model,)
                ).fetchone()
                if row is None:
                    return
                raise ValueError(
                    f"cannot release {quantity} of {model}: only {row['reserved']} reserved"
                )
            row = conn.execute(
                "SELECT location FROM stock_quant WHERE model = ?", (model,)
            ).fetchone()
            self._record_move(conn, "release", model, quantity, row["location"], order_id)

    def receive(self, model: str, quantity: int) -> str:
        """入库，返回 location。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT location FROM stock_quant WHERE model = ?", (model,)
            ).fetchone()
            if row is None:
                return ""
            conn.execute(
                "UPDATE stock_quant SET quantity = quantity + ?, inbound_date = ?, "
                "updated_at = datetime('now') WHERE model = ?",
                (quantity, date.today().isoformat(), model),
            )
            self._record_move(conn, "receive", model, quantity, row["location"])
            return row["location"]

    def scrap(self, model: str, quantity: int, order_id: str = "", reason: str = "") -> bool:
        """报废出库：扣减在库量并登记 scrap 履历。

        只允许报废未被预留的可用库存；超出可用量抛 ValueError，
        型号不存在返回 False。
        """
        if quantity <= 0:
            raise ValueError(f"scrap quantity must be positive, got {quantity}")
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE stock_quant SET quantity = quantity - ?, scrap_date = ?, "
                "updated_at = datetime('now') "
                "WHERE model = ? AND quantity - reserved >= ?",
                (quantity, date.today().isoformat(), model, quantity),
            )
            if cur.rowcount == 0:
                row = conn.execute(
                    "SELECT quantity, reserved FROM stock_quant WHERE model = ?",
                    (model,),
                ).fetchone()
                if row is None:
                    return False
                available = row["quantity"] - row["reserved"]
                raise ValueError(
                    f"cannot scrap {quantity} of {model}: only {available} available"
                )
            row = conn.execute(
                "SELECT location FROM stock_quant WHERE model = ?", (model,)
            ).fetchone()
            self._record_move(conn, "scrap", model, quantity, row["location"], order_id, reason)
            return True

    def set_life_expectancy(self, model: str, weeks: int) -> None:
        """设置备件预期使用寿命（周），0 表示不参与寿命预警。"""
        if weeks < 0:
            raise ValueError(f"expected life weeks must be >= 0, got {weeks}")
        with self._conn() as conn:
            conn.execute(
                "UPDATE stock_quant SET expected_life_weeks = ?, "
                "updated_at = datetime('now') WHERE model = ?",
                (weeks, model),
            )

    def get_lifecycle(self, model: str) -> list[dict]:
        """按时间顺序返回某型号的全生命周期履历（入库→预留→确认→释放→报废）。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, move_type, model, quantity, location, order_id, note, created_at "
                "FROM stock_move WHERE model = ? ORDER BY id",
                (model,),
            ).fetchall()
        return [dict(row) for row in rows]

    def weekly_demand_history(self, model: str, weeks: int = 8) -> list[int]:
        """从 confirm 出库履历派生每周需求历史（旧→新），供需求预测使用。"""
        if weeks <= 0:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT quantity, created_at FROM stock_move "
                "WHERE model = ? AND move_type = 'confirm' "
                "AND created_at >= datetime('now', ?)",
                (model, f"-{weeks * 7} days"),
            ).fetchall()
        history = [0] * weeks
        # sqlite datetime('now') 为 UTC，这里同样取 UTC 计算周龄
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for row in rows:
            try:
                created = datetime.fromisoformat(row["created_at"])
            except ValueError:
                continue
            idx = weeks - 1 - (now - created).days // 7
            if 0 <= idx < weeks:
                history[idx] += row["quantity"]
        return history

    def list_items(self) -> list[InventoryItem]:
        """返回全部在库条目（含生命周期字段），供预警扫描与 MCP 查询使用。"""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM stock_quant ORDER BY model").fetchall()
        return [self._row_to_item(row) for row in rows]

    def list_life_warnings(self, warn_weeks: int = 2) -> list[dict]:
        """返回寿命到期(expired)或临期(expiring)的备件清单。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT model, part_name, location, quantity, inbound_date, "
                "expected_life_weeks FROM stock_quant "
                "WHERE expected_life_weeks > 0 AND inbound_date != '' AND quantity > 0"
            ).fetchall()
        warnings = []
        for row in rows:
            risk = classify_life_risk(
                row["inbound_date"], row["expected_life_weeks"], warn_weeks=warn_weeks
            )
            if risk in ("expired", "expiring"):
                warnings.append({**dict(row), "life_risk": risk})
        return warnings

    def query(self, model: str) -> InventoryItem | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM stock_quant WHERE model = ?", (model,)
            ).fetchone()
        return self._row_to_item(row) if row else None

    def query_by_name(self, part_name: str) -> InventoryItem | None:
        """模糊匹配中文名或英文名，优先返回可用库存最多的条目。"""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM stock_quant
                   WHERE (part_name LIKE ? OR en_name LIKE ?)
                   ORDER BY (quantity - reserved) DESC
                   LIMIT 1""",
                (f"%{part_name}%", f"%{part_name}%"),
            ).fetchone()
        return self._row_to_item(row) if row else None

    def get_status(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT location, quantity FROM stock_quant"
            ).fetchall()
        return {row["location"]: row["quantity"] for row in rows}

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> InventoryItem:
        return InventoryItem(
            model=row["model"],
            part_name=row["part_name"],
            en_name=row["en_name"],
            quantity=row["quantity"],
            reserved=row["reserved"],
            available=row["quantity"] - row["reserved"],
            location=row["location"],
            zone=row["zone"],
            max_capacity=row["max_capacity"],
            inbound_date=row["inbound_date"],
            expected_life_weeks=row["expected_life_weeks"],
            scrap_date=row["scrap_date"],
        )
