# src/api/queue_manager.py
import time
from collections import deque
from src.warehouse.models import WorkOrder, OrderPriority

WINDOW_SECONDS = 30
SIZE_THRESHOLD = 10


class OrderQueue:
    def __init__(self, window_seconds: int = WINDOW_SECONDS,
                 size_threshold: int = SIZE_THRESHOLD):
        self._queue:        deque[WorkOrder] = deque()
        self._urgent_queue: deque[WorkOrder] = deque()
        self._last_flush_time = time.time()
        self.window_seconds  = window_seconds
        self.size_threshold  = size_threshold

    def push(self, order: WorkOrder) -> None:
        if order.priority == OrderPriority.URGENT:
            self._urgent_queue.append(order)
        else:
            self._queue.append(order)

    def should_flush(self) -> bool:
        if self._urgent_queue:
            return True
        if len(self._queue) >= self.size_threshold:
            return True
        if self._queue and (time.time() - self._last_flush_time >= self.window_seconds):
            return True
        return False

    def drain(self) -> list[WorkOrder]:
        orders: list[WorkOrder] = []
        while self._urgent_queue:
            orders.append(self._urgent_queue.popleft())
        while self._queue:
            orders.append(self._queue.popleft())
        self._last_flush_time = time.time()
        return orders

    def size(self) -> int:
        return len(self._queue) + len(self._urgent_queue)
