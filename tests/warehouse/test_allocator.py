# tests/warehouse/test_allocator.py
import pytest
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.pathfinding import PathFinder
from src.warehouse.fleet.tsp import TSPSolver
from src.warehouse.fleet.allocator import TaskAllocator
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.models import (
    TransportTask, TaskCluster, AGVState, TaskType, OrderPriority, AblationFlags,
)

import src.warehouse.maps.medium_50x50  # noqa: F401


@pytest.fixture
def allocator():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    pf = PathFinder(wmap, config)
    tsp = TSPSolver(pf, config)
    return TaskAllocator(pf, tsp, config), wmap


def _make_cluster(cid, task_count, priority=OrderPriority.NORMAL):
    tasks = [
        TransportTask(task_id=cid * 100 + i, task_type=TaskType.OUTBOUND,
                      dest=f"Raw1_S{i % 4 + 1}", priority=priority)
        for i in range(task_count)
    ]
    return TaskCluster(cluster_id=cid, tasks=tasks, task_num=task_count,
                       order_ids=[1], priority=priority)


def test_allocate_empty(allocator):
    alloc, wmap = allocator
    agvs = [AGVState(agv_id=1, init_pos=(8, 6), current_pos=(8, 6))]
    result, ms = alloc.allocate([], agvs, wmap.zone_pos)
    assert ms == 0


def test_allocate_single_cluster(allocator):
    alloc, wmap = allocator
    clusters = [_make_cluster(1, 3)]
    agvs = [AGVState(agv_id=i, init_pos=p, current_pos=p)
            for i, p in enumerate([(8, 6), (22, 6)], 1)]
    result, ms = alloc.allocate(clusters, agvs, wmap.zone_pos)
    total_assigned = sum(len(v) for v in result.values())
    assert total_assigned == 1
    assert ms > 0


def test_allocate_multiple_clusters(allocator):
    alloc, wmap = allocator
    clusters = [_make_cluster(i, 3) for i in range(1, 5)]
    agvs = [AGVState(agv_id=i, init_pos=p, current_pos=p)
            for i, p in enumerate([(8, 6), (22, 6), (36, 6), (8, 22)], 1)]
    result, ms = alloc.allocate(clusters, agvs, wmap.zone_pos)
    total = sum(len(v) for v in result.values())
    assert total == 4


def test_greedy_fallback():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig(ablation=AblationFlags(enable_cp_sat=False))
    pf = PathFinder(wmap, config)
    tsp = TSPSolver(pf, config)
    alloc = TaskAllocator(pf, tsp, config)
    clusters = [_make_cluster(i, 2) for i in range(1, 4)]
    agvs = [AGVState(agv_id=i, init_pos=p, current_pos=p)
            for i, p in enumerate([(8, 6), (22, 22)], 1)]
    result, ms = alloc.allocate(clusters, agvs, wmap.zone_pos)
    total = sum(len(v) for v in result.values())
    assert total == 3
