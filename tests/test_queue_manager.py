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


# ── asyncio.Event + requeue ──

async def test_wait_for_flush_returns_on_urgent():
    q = OrderQueue()

    async def push_later():
        await asyncio.sleep(0.05)
        q.push(_urgent_order())

    asyncio.create_task(push_later())
    await q.wait_for_flush()
    assert q.size() > 0


async def test_requeue_puts_orders_back():
    q = OrderQueue()
    orders = [_normal_order(1), _normal_order(2)]
    ok = q.requeue(orders)
    assert ok is True
    assert q.size() == 2


async def test_requeue_exceeds_max_retries():
    q = OrderQueue(max_retries=0)
    orders = [_normal_order(1)]
    ok = q.requeue(orders)
    assert ok is False
    assert q.size() == 0
