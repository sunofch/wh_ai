# src/warehouse/wms/order_manager.py
from __future__ import annotations
import random

from src.warehouse.models import (
    WorkOrder, OrderItem, OrderPriority, TaskType, MapConfig,
)

_ACTION_MAP = {
    "入库": TaskType.INBOUND,
    "出库": TaskType.OUTBOUND,
    "调库": TaskType.TRANSFER,
}


class OrderManager:
    def __init__(self, map_config: MapConfig, seed: int = 42):
        self.config = map_config
        self.seed = seed
        self.inbound_ports = [
            name for name, cfg in map_config.ports.items()
            if cfg["type"] == "INBOUND"
        ]
        self.outbound_ports = [
            name for name, cfg in map_config.ports.items()
            if cfg["type"] == "OUTBOUND"
        ]

    def from_random(self, count: int,
                    min_items: int = 2, max_items: int = 6) -> list[WorkOrder]:
        """生成随机工单"""
        rng = random.Random(self.seed)
        orders = []
        for i in range(count):
            is_urgent = rng.random() < 0.1
            priority = OrderPriority.URGENT if is_urgent else OrderPriority.NORMAL
            n_items = rng.randint(min_items, max_items)
            items = []
            for j in range(n_items):
                task_type = rng.choice(list(TaskType))
                port = (rng.choice(self.inbound_ports)
                        if task_type == TaskType.INBOUND
                        else rng.choice(self.outbound_ports))
                items.append(OrderItem(
                    item_id=j + 1,
                    task_type=task_type,
                    quantity=rng.randint(1, 5),
                    target_location=port,
                ))
            orders.append(WorkOrder(
                order_id=i + 1, source="random", priority=priority, items=items
            ))
        return orders

    def from_port_instruction(self, instruction, inventory_db=None) -> WorkOrder | None:
        """从 PortInstruction 生成工单。

        inventory_db 可选，提供时按 model/part_name 解析真实储位。
        """
        if all(v is None for v in [
            instruction.part_name, instruction.model,
            instruction.quantity, instruction.action_required,
        ]):
            return None

        rng = random.Random(self.seed)
        task_type = _ACTION_MAP.get(
            instruction.action_required or "", TaskType.OUTBOUND
        )
        priority = (OrderPriority.URGENT if instruction.is_urgent
                    else OrderPriority.NORMAL)

        # 自动分配端口
        if task_type == TaskType.INBOUND:
            port = rng.choice(self.inbound_ports) if self.inbound_ports else ""
        else:
            port = rng.choice(self.outbound_ports) if self.outbound_ports else ""

        # 通过 StockManager 解析储位
        resolved_pick = ""
        resolved_dest = ""
        if inventory_db is not None:
            inv_item = None
            if instruction.model:
                inv_item = inventory_db.query(instruction.model)
            if inv_item is None and instruction.part_name:
                inv_item = inventory_db.query_by_name(instruction.part_name)
            if inv_item:
                if task_type == TaskType.OUTBOUND:
                    resolved_pick = inv_item.location
                    resolved_dest = port
                elif task_type == TaskType.INBOUND:
                    resolved_pick = port
                    resolved_dest = inv_item.location
                else:  # TRANSFER
                    resolved_pick = inv_item.location
                    resolved_dest = port

        item = OrderItem(
            item_id=1,
            task_type=task_type,
            model=instruction.model or "",
            part_name=instruction.part_name or "",
            quantity=instruction.quantity or 1,
            resolved_pick=resolved_pick,
            resolved_dest=resolved_dest,
        )
        return WorkOrder(
            order_id=1,
            source="vlm",
            priority=priority,
            items=[item],
            metadata={
                "description": instruction.description,
                "raw_text": instruction.description or "",
            },
        )
