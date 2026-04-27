# tests/warehouse/test_tsp.py
import pytest
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.pathfinding import PathFinder
from src.warehouse.fleet.tsp import TSPSolver
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.models import TransportTask, TaskType, OrderPriority, AblationFlags

import src.warehouse.maps.medium_50x50  # noqa: F401


@pytest.fixture
def tsp_solver():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    pf = PathFinder(wmap, config)
    return TSPSolver(pf, config), wmap


def test_tsp_single_task(tsp_solver):
    solver, wmap = tsp_solver
    tasks = [TransportTask(task_id=1, task_type=TaskType.OUTBOUND, dest="Raw1_S1")]
    result, dist = solver.optimize(tasks, (8, 6), wmap.zone_pos)
    assert len(result) == 1
    assert dist >= 0


def test_tsp_empty_tasks(tsp_solver):
    solver, wmap = tsp_solver
    result, dist = solver.optimize([], (8, 6), wmap.zone_pos)
    assert result == []
    assert dist == 0


def test_tsp_multiple_tasks(tsp_solver):
    solver, wmap = tsp_solver
    tasks = [
        TransportTask(task_id=i, task_type=TaskType.OUTBOUND, dest=dest)
        for i, dest in enumerate(["Raw1_S1", "Finished1_S1", "Spare1_S1"], 1)
    ]
    result, dist = solver.optimize(tasks, (8, 6), wmap.zone_pos)
    assert len(result) == 3
    assert dist > 0


def test_tsp_disabled():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig(ablation=AblationFlags(enable_tsp=False))
    pf = PathFinder(wmap, config)
    solver = TSPSolver(pf, config)
    tasks = [
        TransportTask(task_id=1, task_type=TaskType.OUTBOUND, dest="Raw1_S1", priority=OrderPriority.LOW),
        TransportTask(task_id=2, task_type=TaskType.OUTBOUND, dest="Finished1_S1", priority=OrderPriority.URGENT),
    ]
    result, dist = solver.optimize(tasks, (8, 6), wmap.zone_pos)
    # 禁用TSP时按优先级降序排列
    assert result[0].priority == OrderPriority.URGENT
