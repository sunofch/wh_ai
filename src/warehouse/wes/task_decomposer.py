# src/warehouse/wes/task_decomposer.py
"""WorkOrder → TransportTask 分解

为每个OrderItem分配具体的pick/dest位置:
  - INBOUND: pick=入库端口(随机选), dest=货架储位(选有空位的)
  - OUTBOUND/TRANSFER: pick=货架储位(选有库存的), dest=出库端口(随机选)
"""

from __future__ import annotations
import random
from src.warehouse.models import (
    WorkOrder, OrderItem, TransportTask, TaskType, OrderPriority,
)
from src.warehouse.wms.inventory import InventoryManager


class TaskDecomposer:
    def __init__(self, inventory: InventoryManager | None, inbound_ports: list[str],
                 outbound_ports: list[str], seed: int = 42):
        self.inventory = inventory
        self.inbound_ports = inbound_ports
        self.outbound_ports = outbound_ports
        self.seed = seed
        self._task_counter = 0

    def decompose(self, work_orders: list[WorkOrder],
                  storage_names: list[str] | None = None) -> list[TransportTask]:
        """将工单分解为运输任务"""
        rng = random.Random(self.seed)
        tasks = []
        if storage_names is None:
            storage_names = self.inventory.get_storage_names()

        storage_inv = {s: 0 for s in storage_names}

        for order in work_orders:
            for item in order.items:
                self._task_counter += 1
                pick, dest = self._resolve_locations(
                    item, storage_names, storage_inv, rng
                )
                tasks.append(TransportTask(
                    task_id=self._task_counter,
                    task_type=item.task_type,
                    priority=order.priority,
                    pick=pick,
                    dest=dest,
                    model=item.model,
                    quantity=item.quantity,
                    order_id=order.order_id,
                ))
        return tasks

    def _resolve_locations(self, item: OrderItem, storage_names: list[str],
                           storage_inv: dict, rng: random.Random) -> tuple[str, str]:
        # 优先使用 InventoryDB 已解析的位置
        if item.resolved_pick and item.resolved_dest:
            return item.resolved_pick, item.resolved_dest

        if item.task_type == TaskType.INBOUND:
            port = item.resolved_pick or rng.choice(self.inbound_ports)
            if item.resolved_dest:
                return port, item.resolved_dest
            available = [s for s in storage_names if storage_inv.get(s, 0) < 3]
            if not available:
                available = storage_names
            dest = rng.choice(available)
            storage_inv[dest] = storage_inv.get(dest, 0) + 1
            return port, dest
        else:
            port = item.resolved_dest or rng.choice(self.outbound_ports)
            if item.resolved_pick:
                return item.resolved_pick, port
            available = [s for s in storage_names if storage_inv.get(s, 0) > 0]
            if not available:
                available = storage_names
            pick = rng.choice(available)
            storage_inv[pick] = max(0, storage_inv.get(pick, 0) - 1)
            return pick, port
