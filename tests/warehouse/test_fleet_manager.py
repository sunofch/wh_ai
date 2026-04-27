# tests/warehouse/test_fleet_manager.py
import pytest
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.fleet_manager import FleetManager
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.models import TransportTask, TaskCluster, TaskType

import src.warehouse.maps.medium_50x50  # noqa: F401


@pytest.fixture
def fleet():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    fm = FleetManager(wmap, config)
    fm.precompute()
    return fm, wmap


def _make_clusters(n_clusters, tasks_per_cluster):
    clusters = []
    for c in range(n_clusters):
        tasks = [
            TransportTask(task_id=c * 100 + i, task_type=TaskType.OUTBOUND,
                          dest=f"Raw{(i % 2) + 1}_S{(i % 4) + 1}")
            for i in range(tasks_per_cluster)
        ]
        clusters.append(TaskCluster(
            cluster_id=c + 1, tasks=tasks, task_num=len(tasks), order_ids=[1]
        ))
    return clusters


def test_schedule_empty(fleet):
    fm, _ = fleet
    agv_tasks, ms = fm.schedule([])
    assert ms == 0
    assert len(agv_tasks) > 0


def test_schedule_clusters(fleet):
    fm, _ = fleet
    clusters = _make_clusters(4, 3)
    agv_tasks, ms = fm.schedule(clusters)
    total = sum(len(v) for v in agv_tasks.values())
    assert total == 12
    assert ms > 0


def test_precompute_populates_cache(fleet):
    fm, _ = fleet
    assert len(fm.path_finder._path_cache) > 0
