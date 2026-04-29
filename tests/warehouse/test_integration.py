# tests/warehouse/test_integration.py
"""端到端集成测试 — 完整管道"""

from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.fleet_manager import FleetManager
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.wms.order_manager import OrderManager
from src.warehouse.wes.task_decomposer import TaskDecomposer
from src.warehouse.wes.clustering import OrderClusterer
from src.warehouse.simulation.simulator import Simulator
import src.warehouse.maps.medium_50x50


def test_full_pipeline():
    """端到端：地图→订单→分解→聚类→调度→仿真"""
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig(ORDER_NUM=10)

    fleet = FleetManager(wmap, config)
    fleet.precompute()

    om = OrderManager(cfg, seed=config.RANDOM_SEED)
    orders = om.from_random(10)
    assert len(orders) == 10

    td = TaskDecomposer(None, om.inbound_ports, om.outbound_ports, seed=config.RANDOM_SEED)
    tasks = td.decompose(orders, wmap.storage_list)
    assert len(tasks) > 0

    clusterer = OrderClusterer(fleet.path_finder, config)
    clusters = clusterer.cluster(tasks, config.AGV_MAX_TASK_CAPACITY, wmap.zone_pos)
    assert len(clusters) > 0

    agv_tasks, est = fleet.schedule(clusters)
    assert est > 0

    sim = Simulator(wmap, fleet, config)
    result = sim.run(agv_tasks, est)
    assert result.makespan > 0
    assert result.total_distance > 0
    assert result.agv_utilization >= 0


def test_pipeline_no_cache():
    """禁用缓存也能运行"""
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    from src.warehouse.models import AblationFlags
    config = WarehouseConfig(
        ORDER_NUM=5,
        ablation=AblationFlags(enable_path_cache=False),
    )

    fleet = FleetManager(wmap, config)
    fleet.precompute()

    om = OrderManager(cfg, seed=config.RANDOM_SEED)
    orders = om.from_random(5)
    td = TaskDecomposer(None, om.inbound_ports, om.outbound_ports, seed=config.RANDOM_SEED)
    tasks = td.decompose(orders, wmap.storage_list)

    clusterer = OrderClusterer(fleet.path_finder, config)
    clusters = clusterer.cluster(tasks, config.AGV_MAX_TASK_CAPACITY, wmap.zone_pos)

    agv_tasks, est = fleet.schedule(clusters)
    sim = Simulator(wmap, fleet, config)
    result = sim.run(agv_tasks, est)
    assert result.makespan > 0
