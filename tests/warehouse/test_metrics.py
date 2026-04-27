# tests/warehouse/test_metrics.py
from src.warehouse.simulation.agv import AGV
from src.warehouse.simulation.metrics import MetricsCollector
from src.warehouse.fleet.pathfinding import SpaceTimeTable


def test_collect_empty():
    agv = AGV(1, (8, 6), max_steps=100)
    st = SpaceTimeTable(50)
    result = MetricsCollector.collect([agv], 0, 0.1, st)
    assert result.makespan == 0
    assert result.agv_utilization == 0.0


def test_collect_with_movement():
    agv = AGV(1, (8, 6), max_steps=100)
    st = SpaceTimeTable(50)
    path = [(8, 6), (9, 6), (10, 6)]
    agv.record_path(path, 0, "moving_empty", 1)
    result = MetricsCollector.collect([agv], 3, 0.5, st)
    assert result.total_distance >= 2  # 2 steps moved


def test_compare():
    from src.warehouse.models import SimulationResult
    r1 = SimulationResult(makespan=100, total_distance=500, agv_utilization=0.8, planning_time=1.5)
    r2 = SimulationResult(makespan=80, total_distance=400, agv_utilization=0.9, planning_time=0.8)
    text = MetricsCollector.compare({"Full": r1, "Baseline": r2})
    assert "Full" in text
    assert "Baseline" in text
