# src/warehouse/wms/order_manager.py
"""工单生成"""

from __future__ import annotations
import random

import numpy as np

from src.warehouse.models import (
    WorkOrder, OrderItem, OrderPriority, TaskType, MapConfig,
)


# action_required → TaskType 映射
_ACTION_MAP = {
    "更换": TaskType.OUTBOUND, "领取": TaskType.OUTBOUND, "出库": TaskType.OUTBOUND,
    "入库": TaskType.INBOUND, "补充": TaskType.INBOUND, "补货": TaskType.INBOUND,
}


class OrderManager:
    def __init__(self, map_config: MapConfig, seed: int = 42):
        self.config = map_config
        self.seed = seed
        # 获取端口列表
        self.inbound_ports = [name for name, cfg in map_config.ports.items() if cfg["type"] == "INBOUND"]
        self.outbound_ports = [name for name, cfg in map_config.ports.items() if cfg["type"] == "OUTBOUND"]

    def from_random(self, count: int) -> list[WorkOrder]:
        """生成随机工单"""
        rng = random.Random(self.seed)
        np_rng = np.random.RandomState(self.seed)
        orders = []
        for i in range(count):
            is_urgent = rng.random() < 0.1
            priority = OrderPriority.URGENT if is_urgent else OrderPriority.NORMAL
            n_items = rng.randint(2, 6)
            items = []
            for j in range(n_items):
                task_type = rng.choice(list(TaskType))
                port = (rng.choice(self.inbound_ports) if task_type == TaskType.INBOUND
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

    def from_port_instruction(self, instruction) -> WorkOrder | None:
        """从PortInstruction生成工单"""
        # 检查全空
        if all(v is None for v in [instruction.part_name, instruction.model,
                                    instruction.quantity, instruction.action_required]):
            return None

        model = instruction.model or ""
        quantity = instruction.quantity or 1
        action = instruction.action_required or ""

        # 映射task_type
        task_type = TaskType.OUTBOUND  # 默认
        for key, val in _ACTION_MAP.items():
            if key in action:
                task_type = val
                break

        item = OrderItem(
            item_id=1, task_type=task_type, model=model,
            part_name=instruction.part_name or "",
            quantity=quantity,
            target_location=instruction.location or "",
        )
        return WorkOrder(
            order_id=1, source="vlm", priority=OrderPriority.NORMAL,
            items=[item],
            metadata={
                "installation_equipment": instruction.installation_equipment,
                "description": instruction.description,
            },
        )
