# tests/warehouse/test_order_manager.py
from src.warehouse.maps.base import MapRegistry
from src.warehouse.wms.order_manager import OrderManager
from src.warehouse.models import TaskType

import src.warehouse.maps.medium_50x50  # noqa: F401


def test_random_orders():
    cfg = MapRegistry.get("medium_50x50")
    om = OrderManager(cfg)
    orders = om.from_random(10)
    assert len(orders) == 10
    assert all(o.source == "random" for o in orders)


def test_from_port_instruction():
    cfg = MapRegistry.get("medium_50x50")
    om = OrderManager(cfg)

    class FakeInstruction:
        part_name = "电机"
        quantity = 5
        model = "M200"
        action_required = "领取"
        location = "1号桥吊"
        installation_equipment = None
        description = None

    order = om.from_port_instruction(FakeInstruction())
    assert order is not None
    assert order.source == "vlm"
    assert len(order.items) == 1
    assert order.items[0].task_type == TaskType.OUTBOUND


def test_from_port_instruction_inbound():
    cfg = MapRegistry.get("medium_50x50")
    om = OrderManager(cfg)

    class FakeInstruction:
        part_name = "传感器"
        quantity = 10
        model = "M300"
        action_required = "入库"
        location = ""
        installation_equipment = None
        description = None

    order = om.from_port_instruction(FakeInstruction())
    assert order is not None
    assert order.items[0].task_type == TaskType.INBOUND


def test_from_port_instruction_empty():
    cfg = MapRegistry.get("medium_50x50")
    om = OrderManager(cfg)

    class FakeInstruction:
        part_name = None
        quantity = None
        model = None
        action_required = None
        location = None
        installation_equipment = None
        description = None

    order = om.from_port_instruction(FakeInstruction())
    assert order is None
