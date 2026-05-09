#!/usr/bin/env python3
"""多种子消融实验 — 检验各模块的稳定性"""

import sys
import numpy as np
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.models import AblationFlags
from main_simulation import run_single

SEEDS = [42, 2024, 7, 123, 999]
ORDER_NUM = 40
MAP_NAME = "medium_57x47"

ABLATION_GROUPS = [
    ("Baseline", AblationFlags(enable_path_cache=False, enable_clustering=False, enable_tsp=False, enable_batch=False)),
    ("M1 缓存", AblationFlags(enable_clustering=False, enable_tsp=False, enable_batch=False)),
    ("M1+M2 聚类", AblationFlags(enable_tsp=False, enable_batch=False)),
    ("M1+M2+M3 TSP", AblationFlags(enable_batch=False)),
    ("M1+M2+M3+M4 Batch", AblationFlags()),
]


def main():
    # 收集数据
    data = {name: [] for name, _ in ABLATION_GROUPS}
    metric_keys = ["makespan", "total_distance", "agv_utilization"]

    for seed in SEEDS:
        print(f"\n=== Seed {seed} ===")
        for name, flags in ABLATION_GROUPS:
            cfg = WarehouseConfig(ablation=flags, ORDER_NUM=ORDER_NUM, RANDOM_SEED=seed)
            result, _, _, _ = run_single(cfg, MAP_NAME, ORDER_NUM)
            data[name].append({
                "makespan": result.makespan,
                "total_distance": result.total_distance,
                "agv_utilization": result.agv_utilization,
                "planning_time": result.planning_time,
            })
            print(f"  {name:<22} makespan={result.makespan:<6} dist={result.total_distance:<6} util={result.agv_utilization:.2%}  time={result.planning_time:.2f}s")

    # 汇总表
    print(f"\n{'='*90}")
    print(f"汇总 (seeds={SEEDS})")
    print(f"{'='*90}")
    print(f"{'实验':<22} {'makespan':>10} {'±':>4} {'dist':>8} {'±':>4} {'util':>8} {'±':>4}")
    print("-" * 90)

    baseline_ms = None
    for name, _ in ABLATION_GROUPS:
        ms = [d["makespan"] for d in data[name]]
        dist = [d["total_distance"] for d in data[name]]
        util = [d["agv_utilization"] for d in data[name]]

        ms_mean, ms_std = np.mean(ms), np.std(ms)
        d_mean, d_std = np.mean(dist), np.std(dist)
        u_mean, u_std = np.mean(util) * 100, np.std(util) * 100

        line = f"{name:<22} {ms_mean:>8.0f} {ms_std:>4.0f} {d_mean:>8.0f} {d_std:>4.0f} {u_mean:>7.1f}% {u_std:>3.1f}%"

        if baseline_ms is not None:
            pct = (ms_mean - baseline_ms) / baseline_ms * 100
            line += f"  ({pct:+.1f}%)"
        else:
            baseline_ms = ms_mean

        print(line)

    # 逐种子对比
    print(f"\n{'='*90}")
    print("逐种子 makespan 对比")
    print(f"{'='*90}")
    header = f"{'实验':<22}" + "".join(f"  seed={s:<6}" for s in SEEDS)
    print(header)
    print("-" * 90)
    for name, _ in ABLATION_GROUPS:
        ms = [d["makespan"] for d in data[name]]
        line = f"{name:<22}" + "".join(f"  {v:<8}" for v in ms)
        print(line)


if __name__ == "__main__":
    main()
