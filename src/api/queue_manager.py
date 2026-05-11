# src/api/queue_manager.py
import asyncio
import time
from collections import deque
from src.warehouse.models import WorkOrder, OrderPriority

WINDOW_SECONDS = 30
SIZE_THRESHOLD = 10
MAX_RETRIES = 1


class OrderQueue:
    def __init__(self, window_seconds: int = WINDOW_SECONDS,
                 size_threshold: int = SIZE_THRESHOLD,
                 max_retries: int = MAX_RETRIES):
        self._queue:        deque[WorkOrder] = deque()
        self._urgent_queue: deque[WorkOrder] = deque()
        self._last_flush_time = time.time()
        self.window_seconds  = window_seconds
        self.size_threshold  = size_threshold
        self.max_retries     = max_retries
        self._event: asyncio.Event | None = None
        self._retry_counts: dict[int, int] = {}

    def _get_event(self) -> asyncio.Event:
        if self._event is None:
            self._event = asyncio.Event()
        return self._event

    def push(self, order: WorkOrder) -> None:
        if order.priority == OrderPriority.URGENT:
            self._urgent_queue.append(order)
        else:
            if not self._queue:
                self._last_flush_time = time.time()
            self._queue.append(order)
        self._get_event().set()

    def should_flush(self) -> bool:
        if self._urgent_queue:
            return True
        if len(self._queue) >= self.size_threshold:
            return True
        if self._queue and (time.time() - self._last_flush_time >= self.window_seconds):
            return True
        return False

    async def wait_for_flush(self) -> None:
        """事件驱动：有订单可刷时返回，否则等待通知。"""
        while True:
            if self.should_flush():
                return
            self._get_event().clear()
            await self._get_event().wait()

    def drain(self) -> list[WorkOrder]:
        orders: list[WorkOrder] = []
        while self._urgent_queue:
            orders.append(self._urgent_queue.popleft())
        while self._queue:
            orders.append(self._queue.popleft())
        self._last_flush_time = time.time()
        self._get_event().clear()
        return orders

    def requeue(self, orders: list[WorkOrder]) -> bool:
        """失败批次重入队，超过重试次数返回 False。"""
        for order in orders:
            count = self._retry_counts.get(order.order_id, 0)
            if count >= self.max_retries:
                return False
        for order in orders:
            self._retry_counts[order.order_id] = \
                self._retry_counts.get(order.order_id, 0) + 1
            if order.priority == OrderPriority.URGENT:
                self._urgent_queue.append(order)
            else:
                self._queue.append(order)
        self._get_event().set()
        return True

    def size(self) -> int:
        return len(self._queue) + len(self._urgent_queue)
