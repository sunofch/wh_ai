# src/warehouse/wms/inventory.py
"""库存管理"""

from __future__ import annotations
from typing import TYPE_CHECKING
import random

import numpy as np

from src.warehouse.models import InventoryItem, MapConfig

if TYPE_CHECKING:
    pass


class InventoryManager:
    def __init__(self, map_config: MapConfig, seed: int = 42):
        self.config = map_config
        self._items: dict[str, InventoryItem] = {}  # model → item
        self._storage_status: dict[str, int] = {}     # storage_name → quantity
        self._init_inventory(seed)

    def _init_inventory(self, seed: int):
        rng = random.Random(seed)
        # 为每个储位分配随机库存
        model_names = [f"M{i * 100}" for i in range(1, 20)]
        part_names = ["电机", "液压泵", "传感器", "控制器", "齿轮箱",
                      "密封件", "轴承", "阀门", "电缆", "过滤器",
                      "联轴器", "制动器", "气缸", "油管", "开关",
                      "继电器", "风扇", "散热器", "螺栓"]

        idx = 0
        for wh_name, wcfg in self.config.warehouse_zones.items():
            zone_prefix = wh_name.split("_")[0] if "_" in wh_name else wh_name
            zone = "".join(c for c in zone_prefix if not c.isdigit()) or "Misc"
            for si in range(1, 5):
                sname = f"{wh_name}_S{si}"
                qty = rng.randint(0, 3)
                model = model_names[idx % len(model_names)]
                self._storage_status[sname] = qty
                if model not in self._items:
                    self._items[model] = InventoryItem(
                        model=model,
                        part_name=part_names[idx % len(part_names)],
                        quantity=qty,
                        location=sname,
                        zone=zone,
                    )
                idx += 1

    def query_by_model(self, model: str) -> InventoryItem | None:
        return self._items.get(model)

    def query_by_zone(self, zone: str) -> list[InventoryItem]:
        return [item for item in self._items.values() if zone in item.zone]

    def allocate_stock(self, model: str, quantity: int) -> str:
        """扣减库存，返回储位名"""
        item = self._items.get(model)
        if item is None:
            # 模糊匹配 part_name
            for m, it in self._items.items():
                if it.part_name == model or model in it.part_name:
                    item = it
                    break
        if item is None:
            return ""
        if item.quantity >= quantity:
            item.quantity -= quantity
            self._storage_status[item.location] = item.quantity
            return item.location
        return ""

    def receive_stock(self, model: str, quantity: int, zone: str = "") -> str:
        """入库，返回储位名"""
        item = self._items.get(model)
        if item is None:
            return ""
        item.quantity += quantity
        self._storage_status[item.location] = item.quantity
        return item.location

    def get_all_locations(self) -> dict[str, tuple[int, int]]:
        """仅返回有库存的储位"""
        from src.warehouse.fleet.map_builder import WarehouseMap
        # 需要MapConfig中的zone_pos，由外部传入
        return {}

    def get_status(self) -> dict[str, int]:
        return dict(self._storage_status)

    def get_all_zone_names(self) -> list[str]:
        """返回所有仓库区名"""
        return list(self.config.warehouse_zones.keys())

    def get_storage_names(self) -> list[str]:
        """返回所有储位名"""
        return list(self._storage_status.keys())
