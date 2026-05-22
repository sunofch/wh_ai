import json
from functools import lru_cache
from langchain_core.tools import tool
from src.warehouse.wms.inventory_db import StockManager


@lru_cache(maxsize=1)
def _get_stock_manager() -> StockManager:
    return StockManager()


@tool
def query_inventory(model: str, part_name: str, quantity: int) -> str:
    """检查指定备件的库存是否满足需求。model 或 part_name 至少提供一个。"""
    db = _get_stock_manager()
    item = db.query(model) if model else None
    if item is None and part_name:
        item = db.query_by_name(part_name)

    if item is None:
        return json.dumps(
            {"available": 0, "location": "", "sufficient": False},
            ensure_ascii=False,
        )

    available = item.quantity - item.reserved
    sufficient = available >= quantity
    return json.dumps(
        {
            "available": available,
            "location": item.location,
            "sufficient": sufficient,
            "shortage": 0 if sufficient else quantity - available,
        },
        ensure_ascii=False,
    )
