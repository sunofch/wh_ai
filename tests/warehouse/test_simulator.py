# tests/warehouse/test_simulator.py
import pytest
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.fleet_manager import FleetManager
from src.warehouse.simulation.simulator import Simulator
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.models import TransportTask, TaskType

import src.warehouse.maps.medium_50x50  # noqa: F401


@pytest.fixture
def sim():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    fleet = FleetManager(wmap, config)
    fleet.precompute()
    return Simulator(wmap, fleet, config), wmap


def test_simulator_empty(sim):
    sim_obj, _ = sim
    result = sim_obj.run({}, 0)
    assert result.makespan >= 0


def test_simulator_with_tasks(sim):
    sim_obj, wmap = sim
    tasks = {
        1: [TransportTask(task_id=1, task_type=TaskType.OUTBOUND, pick="Raw1_S1", dest="出库南")],
        2: [TransportTask(task_id=2, task_type=TaskType.INBOUND, pick="入库北", dest="Finished1_S1")],
    }
    result = sim_obj.run(tasks, 100)
    assert result.makespan > 0
    assert result.total_distance >= 0
