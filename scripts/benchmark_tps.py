#!/usr/bin/env python3
"""库存层 / API 层 TPS 压测脚本。

用法:
    python scripts/benchmark_tps.py                       # 库存层压测
    python scripts/benchmark_tps.py --threads 16 --ops 200
    python scripts/benchmark_tps.py --api http://localhost:8000  # API 层压测

输出 JSON：total_ops / elapsed_s / tps / errors。
对照 pj4 考核指标"高并发场景支持 ≥ 1000 TPS"量化现状；
达标路径（PostgreSQL + 多 Worker + nginx HA）见 docs/date_plan/513plan.md。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run_stock_benchmark(
    db_path: str = "data/bench_inventory.db",
    n_threads: int = 8,
    ops_per_thread: int = 100,
) -> dict:
    """并发混合读写（receive + query）压测 StockManager。"""
    from src.warehouse.maps.base import MapRegistry
    import src.warehouse.maps.medium_57x47  # noqa: F401
    from src.warehouse.wms.inventory_db import StockManager

    mgr = StockManager(db_path=db_path)
    mgr.seed_from_map(MapRegistry.get("medium_57x47"), seed=42)
    model = next(item.model for item in mgr.list_items())

    errors = 0

    def worker(_: int) -> int:
        failed = 0
        for i in range(ops_per_thread):
            try:
                if i % 2 == 0:
                    mgr.receive(model, 1)
                else:
                    mgr.query(model)
            except Exception:
                failed += 1
        return failed

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        errors = sum(pool.map(worker, range(n_threads)))
    elapsed = time.perf_counter() - start

    total_ops = n_threads * ops_per_thread
    return {
        "target": "stock_layer",
        "total_ops": total_ops,
        "elapsed_s": round(elapsed, 3),
        "tps": round(total_ops / elapsed, 1),
        "errors": errors,
    }


def run_api_benchmark(
    base_url: str,
    n_threads: int = 8,
    ops_per_thread: int = 50,
) -> dict:
    """并发 POST /instructions 压测 API（需服务已启动）。"""
    import urllib.error
    import urllib.request

    payload = json.dumps(
        {"text": "出库1个深沟球轴承，型号6208-2RS-C3-SKF"}
    ).encode()

    def worker(_: int) -> int:
        failed = 0
        for _ in range(ops_per_thread):
            req = urllib.request.Request(
                f"{base_url}/instructions",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status >= 400:
                        failed += 1
            except (urllib.error.URLError, TimeoutError):
                failed += 1
        return failed

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        errors = sum(pool.map(worker, range(n_threads)))
    elapsed = time.perf_counter() - start

    total_ops = n_threads * ops_per_thread
    return {
        "target": base_url,
        "total_ops": total_ops,
        "elapsed_s": round(elapsed, 3),
        "tps": round(total_ops / elapsed, 1),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--ops", type=int, default=100, help="每线程操作数")
    parser.add_argument("--api", default="", help="API 地址，给出则压测 API 层")
    parser.add_argument("--db", default="data/bench_inventory.db")
    args = parser.parse_args()

    if args.api:
        report = run_api_benchmark(args.api, args.threads, args.ops)
    else:
        report = run_stock_benchmark(args.db, args.threads, args.ops)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
