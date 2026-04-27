# tests/warehouse/test_integration.py
"""端到端集成测试"""

import pytest
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

import src.warehouse.maps.medium_50x50  # noqa: F401


def _full_pipeline(map_name="medium_50x50", order_num=10, flags=None):
    """完整流水线：订单生成→分解→聚类→调度→仿真"""
    config = WarehouseConfig(
        ablation=flags or AblationFlags(),
        ORDER_NUM=order_num,
        RANDOM_SEED=42,
    )
    np.random.seed(42)
    random.seed(42)

    map_config = MapRegistry.get(map_name)
    wmap = WarehouseMap(map_config)

    fleet = FleetManager(wmap, config)
    fleet.precompute()

    om = OrderManager(map_config, seed=42)
    orders = om.from_random(order_num)

    td = TaskDecomposer(None, om.inbound_ports, om.outbound_ports, seed=42)
    tasks = td.decompose(orders, wmap.storage_list)

    clusterer = OrderClusterer(fleet.path_finder, config)
    clusters = clusterer.cluster(tasks, config.AGV_MAX_TASK_CAPACITY, wmap.zone_pos)

    agv_tasks, makespan = fleet.schedule(clusters)

    sim = Simulator(wmap, fleet, config)
    result = sim.run(agv_tasks, makespan)
    return result


def test_full_pipeline_medium():
    result = _full_pipeline("medium_50x50", 10)
    assert result.makespan > 0
    assert result.total_distance >= 0
    assert 0 <= result.agv_utilization <= 1.0
    assert result.planning_time >= 0


def test_full_pipeline_baseline():
    flags = AblationFlags(
        enable_path_cache=False, enable_clustering=False,
        enable_tsp=False, enable_cp_sat=False, enable_conflict_avoid=False,
    )
    result = _full_pipeline("medium_50x50", 5, flags)
    assert result.makespan > 0


def test_full_pipeline_full():
    result = _full_pipeline("medium_50x50", 10, AblationFlags())
    assert result.makespan > 0
    assert result.agv_utilization > 0


def test_all_maps_runnable():
    """所有地图都能跑通完整流程"""
    import src.warehouse.maps.large_100x100  # noqa: F401
    import src.warehouse.maps.extreme  # noqa: F401

    for name, _ in MapRegistry.list_all():
        result = _full_pipeline(name, 5)
        assert result.makespan > 0, f"Map {name} failed: makespan=0"


def test_ablation_consistency():
    """相同种子、相同配置 → makespan一致（路径缓存导致total_distance可能微变）"""
    r1 = _full_pipeline("medium_50x50", 5)
    r2 = _full_pipeline("medium_50x50", 5)
    assert r1.makespan == r2.makespan
