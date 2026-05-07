#!/usr/bin/env python3
# main_simulation.py
"""
AGV 智能仓储调度系统 v2.0 — 仿真测试入口

====================================
使用说明
====================================

【基本运行】
    python main_simulation.py [地图名] [订单数]

    参数:
        地图名   - 可选，默认 medium_57x47
                  可选值: medium_57x47
        订单数   - 可选，默认 40

【消融实验】
    python main_simulation.py --ablation [地图名] [订单数]

    运行 5 组消融实验对比:
    - Baseline (无优化): 关闭所有模块
    - M1 (路径缓存): 仅启用路径缓存
    - M1+M2 (+聚类): 路径缓存 + 方向感知聚类
    - M1+M2+M3 (+TSP): + 双向 Batch TSP
    - M1+M2+M3+M4 (+CP-SAT): + CP-SAT 全局分配
====================================
运行示例
====================================

# 1. 默认运行 (50x50地图, 40订单)
python main_simulation.py

# 2. 指定地图和订单数
python main_simulation.py medium_57x47 60

# 3. 运行消融实验
python main_simulation.py --ablation

# 4. 消融实验指定订单数
python main_simulation.py --ablation medium_57x47 20

====================================
技术特性
====================================

- 四层架构: WMS → WES → Fleet → Simulation
- 双向 Batch: OUTBOUND 多取一送 + INBOUND 一取多送
- 方向感知聚类: 按 dest/pick 区域智能分组
- 时空 A* 寻路: 避免多 AGV 冲突
- CP-SAT 分配: 全局优化 makespan
- OR-Tools TSP: 任务序列优化
====================================
"""

import sys
import time
import numpy as np
import random

from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.fleet_manager import FleetManager
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.wms.order_manager import OrderManager
from src.warehouse.wes.task_decomposer import TaskDecomposer
from src.warehouse.wes.clustering import OrderClusterer
from src.warehouse.simulation.simulator import Simulator
from src.warehouse.simulation.metrics import MetricsCollector
from src.warehouse.models import AblationFlags

# 注册所有地图
import src.warehouse.maps.medium_57x47  # noqa: F401


def run_single(config: WarehouseConfig, map_name: str, order_num: int):
    """运行单次仿真"""
    map_config = MapRegistry.get(map_name)
    wmap = WarehouseMap(map_config)

    fleet = FleetManager(wmap, config)
    fleet.precompute()

    om = OrderManager(map_config, seed=config.RANDOM_SEED)
    orders = om.from_random(order_num)

    td = TaskDecomposer(None, om.inbound_ports, om.outbound_ports, seed=config.RANDOM_SEED)
    tasks = td.decompose(orders, wmap.storage_list)

    clusterer = OrderClusterer(fleet.path_finder, config)
    clusters = clusterer.cluster(tasks, config.AGV_MAX_TASK_CAPACITY, wmap.zone_pos)

    agv_tasks, estimated_makespan = fleet.schedule(clusters)

    sim = Simulator(wmap, fleet, config)
    result = sim.run(agv_tasks, estimated_makespan)
    return result, wmap, sim, estimated_makespan


def run_ablation(config: WarehouseConfig, map_name: str, order_num: int):
    """消融实验"""
    ablation_groups = [
        {"name": "Baseline (无优化)", "flags": AblationFlags(enable_path_cache=False, enable_clustering=False, enable_tsp=False, enable_cp_sat=False)},
        {"name": "M1 (路径缓存)", "flags": AblationFlags(enable_clustering=False, enable_tsp=False, enable_cp_sat=False)},
        {"name": "M1+M2 (+聚类)", "flags": AblationFlags(enable_tsp=False, enable_cp_sat=False)},
        {"name": "M1+M2+M3 (+TSP)", "flags": AblationFlags(enable_cp_sat=False)},
        {"name": "M1+M2+M3+M4 (+CP-SAT)", "flags": AblationFlags()},
    ]

    results = {}
    for group in ablation_groups:
        print(f"\n{'='*60}")
        print(f"  运行: {group['name']}")
        print(f"{'='*60}")
        cfg = WarehouseConfig(ablation=group["flags"], ORDER_NUM=order_num, RANDOM_SEED=config.RANDOM_SEED)
        result, _, _, est_ms = run_single(cfg, map_name, order_num)
        results[group["name"]] = result
        print(f"  估计makespan: {est_ms} | 实际makespan: {result.makespan} | 距离: {result.total_distance} | 利用率: {result.agv_utilization:.2%} | 耗时: {result.planning_time:.2f}s")

    print(f"\n{'='*100}")
    print("消融实验结果对比")
    print(MetricsCollector.compare(results))
    print(f"{'='*100}")
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("  AGV 智能仓储调度系统 v2.0 — 仿真测试")
    print("=" * 60)

    config = WarehouseConfig()

    args = sys.argv[1:]

    if len(args) > 0 and args[0] == "--ablation":
        map_name = args[1] if len(args) > 1 else config.MAP_NAME
        order_num = int(args[2]) if len(args) > 2 else config.ORDER_NUM
        results = run_ablation(config, map_name, order_num)
    else:
        map_name = args[0] if len(args) > 0 else config.MAP_NAME
        order_num = int(args[1]) if len(args) > 1 else config.ORDER_NUM

        print(f"  地图: {map_name} | 订单数: {order_num}")
        np.random.seed(config.RANDOM_SEED)
        random.seed(config.RANDOM_SEED)

        result, wmap, sim, _ = run_single(config, map_name, order_num)

        print(f"\n  Makespan: {result.makespan}")
        print(f"  总距离: {result.total_distance}")
        print(f"  AGV利用率: {result.agv_utilization:.2%}")
        print(f"  规划耗时: {result.planning_time:.2f}s")

        MetricsCollector.export_json(result, "output/result.json")
        print("\n  结果已保存到 output/result.json")
