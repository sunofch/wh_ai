"""订单队列：内存队列（开发用）+ Redis 队列（生产用）。

RedisOrderQueue 从 Redis List 读取由 Celery Worker 写入的 WorkOrder，
与 scheduler_loop 配合实现批量 Simulator 调度。
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque

from src.warehouse.models import WorkOrder, OrderItem, OrderPriority, TaskType

WINDOW_SECONDS = int(os.getenv("SCHEDULER_WINDOW_SECONDS", "30"))
SIZE_THRESHOLD = int(os.getenv("SCHEDULER_SIZE_THRESHOLD", "10"))
MAX_RETRIES = 1

PENDING_ORDERS_KEY = "warehouse:pending_orders"
URGENT_ORDERS_KEY = "warehouse:pending_orders:urgent"


# ---------------------------------------------------------------------------
# 内存队列（单进程开发/测试用）
# ---------------------------------------------------------------------------

class OrderQueue:
    def __init__(
        self,
        window_seconds: int = WINDOW_SECONDS,
        size_threshold: int = SIZE_THRESHOLD,
        max_retries: int = MAX_RETRIES,
    ):
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
        for order in orders:
            count = self._retry_counts.get(order.order_id, 0)
            if count >= self.max_retries:
                return False
        for order in orders:
            self._retry_counts[order.order_id] = (
                self._retry_counts.get(order.order_id, 0) + 1
            )
            if order.priority == OrderPriority.URGENT:
                self._urgent_queue.append(order)
            else:
                self._queue.append(order)
        self._get_event().set()
        return True

    def size(self) -> int:
        return len(self._queue) + len(self._urgent_queue)


# ---------------------------------------------------------------------------
# Redis 队列（生产用，与 Celery Worker 配合）
# ---------------------------------------------------------------------------

class RedisOrderQueue:
    """从 Redis List 读取 Celery Worker 写入的 WorkOrder，供 scheduler_loop 批量调度。"""

    def __init__(
        self,
        redis_url: str,
        window_seconds: int = WINDOW_SECONDS,
        size_threshold: int = SIZE_THRESHOLD,
        max_retries: int = MAX_RETRIES,
    ):
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self.window_seconds  = window_seconds
        self.size_threshold  = size_threshold
        self.max_retries     = max_retries
        self._retry_counts: dict[int, int] = {}
        self._deadline: float = time.time() + window_seconds

    async def wait_for_flush(self) -> None:
        """轮询 Redis List，积累到阈值或超时则返回。"""
        while True:
            urgent_len = await self._redis.llen(URGENT_ORDERS_KEY)
            if urgent_len > 0:
                return

            normal_len = await self._redis.llen(PENDING_ORDERS_KEY)
            if normal_len >= self.size_threshold:
                return

            if time.time() >= self._deadline:
                if normal_len > 0:
                    self._deadline = time.time() + self.window_seconds
                    return
                self._deadline = time.time() + self.window_seconds

            await asyncio.sleep(1)

    def drain(self) -> list[WorkOrder]:
        raise RuntimeError("RedisOrderQueue.drain() 需在异步上下文使用 drain_async()")

    async def drain_async(self) -> list[WorkOrder]:
        """批量弹出所有待处理订单（紧急优先）。"""
        orders: list[WorkOrder] = []

        # 紧急订单优先
        while True:
            raw = await self._redis.lpop(URGENT_ORDERS_KEY)
            if raw is None:
                break
            order = _dict_to_work_order(json.loads(raw))
            if order:
                orders.append(order)

        # 普通订单
        while True:
            raw = await self._redis.lpop(PENDING_ORDERS_KEY)
            if raw is None:
                break
            order = _dict_to_work_order(json.loads(raw))
            if order:
                orders.append(order)

        self._deadline = time.time() + self.window_seconds
        return orders

    async def requeue_async(self, orders: list[WorkOrder]) -> bool:
        for order in orders:
            count = self._retry_counts.get(order.order_id, 0)
            if count >= self.max_retries:
                return False
        for order in orders:
            self._retry_counts[order.order_id] = (
                self._retry_counts.get(order.order_id, 0) + 1
            )
            data = json.dumps(_work_order_to_dict(order), ensure_ascii=False)
            key = URGENT_ORDERS_KEY if order.priority == OrderPriority.URGENT else PENDING_ORDERS_KEY
            await self._redis.rpush(key, data)
        return True

    async def size(self) -> int:
        n = await self._redis.llen(PENDING_ORDERS_KEY)
        u = await self._redis.llen(URGENT_ORDERS_KEY)
        return n + u

    async def close(self) -> None:
        await self._redis.aclose()


# ---------------------------------------------------------------------------
# 辅助函数：WorkOrder ↔ dict
# ---------------------------------------------------------------------------

def _dict_to_work_order(data: dict) -> WorkOrder | None:
    try:
        items = [
            OrderItem(
                item_id=item["item_id"],
                task_type=TaskType(item["task_type"]),
                model=item.get("model", ""),
                part_name=item.get("part_name", ""),
                quantity=item.get("quantity", 1),
                resolved_pick=item.get("pick", ""),
                resolved_dest=item.get("dest", ""),
            )
            for item in data.get("items", [])
        ]
        return WorkOrder(
            order_id=data["order_id"],
            source=data.get("source", "vlm"),
            priority=OrderPriority(data.get("priority", OrderPriority.NORMAL.value)),
            items=items,
            metadata=data.get("metadata", {}),
        )
    except (KeyError, ValueError):
        return None


def _work_order_to_dict(order: WorkOrder) -> dict:
    return {
        "order_id": order.order_id,
        "source": order.source,
        "priority": order.priority.value,
        "items": [
            {
                "item_id": item.item_id,
                "task_type": item.task_type.value,
                "model": item.model,
                "part_name": item.part_name,
                "quantity": item.quantity,
                "pick": item.resolved_pick,
                "dest": item.resolved_dest,
            }
            for item in order.items
        ],
        "metadata": order.metadata,
    }
