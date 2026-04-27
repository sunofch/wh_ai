# tests/warehouse/test_clustering.py
import pytest
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.pathfinding import PathFinder
from src.warehouse.wes.clustering import OrderClusterer
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.models import TransportTask, TaskType, AblationFlags

import src.warehouse.maps.medium_50x50  # noqa: F401


@pytest.fixture
def clusterer():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    pf = PathFinder(wmap, config)
    return OrderClusterer(pf, config), wmap


def test_cluster_tasks(clusterer):
    cl, wmap = clusterer
    tasks = [
        TransportTask(task_id=i, task_type=TaskType.OUTBOUND,
                      dest=f"Raw{(i % 2) + 1}_S{(i % 4) + 1}")
        for i in range(20)
    ]
    clusters = cl.cluster(tasks, 20, wmap.zone_pos)
    total = sum(c.task_num for c in clusters)
    assert total == 20


def test_cluster_disabled():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig(ablation=AblationFlags(enable_clustering=False))
    pf = PathFinder(wmap, config)
    cl = OrderClusterer(pf, config)
    tasks = [TransportTask(task_id=i, task_type=TaskType.OUTBOUND, dest="Raw1_S1")
             for i in range(5)]
    clusters = cl.cluster(tasks, 20, wmap.zone_pos)
    assert len(clusters) == 5  # 每个任务独立一簇


def test_cluster_capacity_split(clusterer):
    cl, wmap = clusterer
    tasks = [TransportTask(task_id=i, task_type=TaskType.OUTBOUND, dest="Raw1_S1")
             for i in range(25)]
    clusters = cl.cluster(tasks, 10, wmap.zone_pos)
    for c in clusters:
        assert c.task_num <= 10
