import asyncio
import pytest
from src.warehouse.models import WorkOrder, OrderPriority
from src.api.queue_manager import OrderQueue

pytestmark = pytest.mark.asyncio


def _normal_order(order_id: int = 1) -> WorkOrder:
    return WorkOrder(order_id=order_id, source="vlm",
                     priority=OrderPriority.NORMAL, items=[])


def _urgent_order(order_id: int = 99) -> WorkOrder:
    return WorkOrder(order_id=order_id, source="vlm",
                     priority=OrderPriority.URGENT, items=[])


async def test_push_and_drain():
    q = OrderQueue()
    q.push(_normal_order())
    orders = q.drain()
    assert len(orders) == 1


async def test_urgent_order_triggers_flush():
    q = OrderQueue()
    assert not q.should_flush()
    q.push(_urgent_order())
    assert q.should_flush()


async def test_size_threshold_triggers_flush():
    q = OrderQueue(size_threshold=3)
    assert not q.should_flush()
    for i in range(3):
        q.push(_normal_order(i))
    assert q.should_flush()


async def test_drain_clears_queue():
    q = OrderQueue()
    q.push(_normal_order())
    q.drain()
    assert not q.should_flush()


async def test_urgent_orders_drained_first():
    q = OrderQueue()
    q.push(_normal_order(1))
    q.push(_urgent_order(99))
    orders = q.drain()
    assert orders[0].order_id == 99
