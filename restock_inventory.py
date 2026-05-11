#!/usr/bin/env python3
"""一键补充库存：将所有品类库存补至目标数量，并清空预留。

用法:
    python restock_inventory.py           # 默认补至 20
    python restock_inventory.py --qty 50  # 自定义目标数量
"""
import argparse
import sqlite3

DB_PATH = "data/inventory.db"


def restock(target_qty: int = 20):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    rows = conn.execute(
        "SELECT model, part_name, location, quantity, reserved FROM stock_quant"
    ).fetchall()

    if not rows:
        print("库存表为空，请先启动 main_api.py 初始化数据库。")
        conn.close()
        return

    print(f"{'零件名称':<14} {'储位':<20} {'当前库存':>6} {'当前预留':>6} {'补后库存':>6}")
    print("-" * 60)

    for row in rows:
        new_qty = max(row["quantity"], target_qty)
        conn.execute(
            "UPDATE stock_quant SET quantity=?, reserved=0, updated_at=datetime('now') WHERE model=?",
            (new_qty, row["model"]),
        )
        print(f"{row['part_name']:<14} {row['location']:<20} {row['quantity']:>6} {row['reserved']:>6} {new_qty:>6}")

    conn.commit()
    conn.close()
    print(f"\n完成：共更新 {len(rows)} 条记录，预留全部清零，库存不足 {target_qty} 的已补至 {target_qty}。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qty", type=int, default=20, help="目标库存数量（默认 20）")
    args = parser.parse_args()
    restock(args.qty)
