# tests/warehouse/test_task_decomposer.py
from src.warehouse.maps.base import MapRegistry
from src.warehouse.wms.inventory import InventoryManager
from src.warehouse.wes.task_decomposer import TaskDecomposer
from src.warehouse.models import WorkOrder, OrderItem, TaskType, OrderPriority

import src.warehouse.maps.medium_50x50  # noqa: F401


def test_decompose_orders():
    cfg = MapRegistry.get("medium_50x50")
    inv = InventoryManager(cfg)
    td = TaskDecomposer(inv, ["入库北", "备件入库东"], ["出库南", "紧急出库西"])
    orders = [WorkOrder(order_id=1, items=[
        OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=3),
        OrderItem(item_id=2, task_type=TaskType.INBOUND, quantity=2),
    ])]
    tasks = td.decompose(orders)
    assert len(tasks) == 2
    assert all(t.pick for t in tasks)
    assert all(t.dest for t in tasks)


def test_decompose_empty():
    cfg = MapRegistry.get("medium_50x50")
    inv = InventoryManager(cfg)
    td = TaskDecomposer(inv, ["入库北"], ["出库南"])
    tasks = td.decompose([])
    assert tasks == []
