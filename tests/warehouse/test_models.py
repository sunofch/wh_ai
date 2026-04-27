# tests/warehouse/test_models.py
import pytest
from src.warehouse.models import (
    AGVStatus, TaskType, OrderPriority,
    InventoryItem, OrderItem, WorkOrder,
    TransportTask, TaskCluster,
    AGVState, TrajectoryStep,
    SimulationResult, AblationFlags, MapConfig,
)


def test_agv_status_enum():
    assert AGVStatus.IDLE == "idle"
    assert AGVStatus.MOVING_EMPTY == "moving_empty"
    assert AGVStatus.CHARGING == "charging"


def test_task_type_enum():
    assert TaskType.INBOUND == "INBOUND"
    assert TaskType.OUTBOUND == "OUTBOUND"


def test_order_priority_enum():
    assert OrderPriority.URGENT > OrderPriority.NORMAL > OrderPriority.LOW
    assert OrderPriority.URGENT == 10


def test_inventory_item():
    item = InventoryItem(model="M200", part_name="电机", quantity=12, location="Raw1_S2", zone="Raw")
    assert item.model == "M200"
    assert item.max_capacity == 4


def test_work_order():
    order = WorkOrder(order_id=1, source="vlm", items=[
        OrderItem(item_id=1, task_type=TaskType.OUTBOUND, model="M200", quantity=5)
    ])
    assert len(order.items) == 1
    assert order.priority == OrderPriority.NORMAL


def test_transport_task():
    task = TransportTask(task_id=1, task_type=TaskType.INBOUND, pick="入库北", dest="Raw1_S1")
    assert task.priority == OrderPriority.NORMAL
    assert task.quantity == 1


def test_task_cluster():
    tasks = [TransportTask(task_id=i, task_type=TaskType.OUTBOUND, pick="A", dest="B") for i in range(3)]
    cluster = TaskCluster(cluster_id=1, tasks=tasks, task_num=3, order_ids=[1], zone="Raw")
    assert cluster.task_num == 3


def test_agv_state():
    state = AGVState(agv_id=1, init_pos=(8, 6), current_pos=(8, 6))
    assert state.battery == 100
    assert state.status == AGVStatus.IDLE


def test_simulation_result_defaults():
    r = SimulationResult()
    assert r.makespan == 0
    assert r.agv_utilization == 0.0


def test_ablation_flags_defaults():
    flags = AblationFlags()
    assert flags.enable_path_cache is True
    assert flags.enable_cp_sat is True


def test_ablation_flags_custom():
    flags = AblationFlags(enable_tsp=False, enable_cp_sat=False)
    assert flags.enable_tsp is False
    assert flags.enable_cp_sat is False


def test_map_config():
    cfg = MapConfig(
        name="test", display_name="Test", grid_size=10,
        warehouse_zones={"Z1": {"pos": (1, 1), "w": 3, "h": 3}},
        ports={"P1": {"pos": (5, 0), "type": "INBOUND"}},
        agv_init_positions=[(2, 2)],
    )
    assert cfg.grid_size == 10
    assert cfg.agv_count == 8  # default
