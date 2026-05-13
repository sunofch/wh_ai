import json
from langchain_core.tools import tool
from src.warehouse.wms.inventory_db import StockManager


@tool
def query_inventory(model: str, part_name: str, quantity: int) -> str:
    """检查指定备件的库存是否满足需求。model 或 part_name 至少提供一个。"""
    db = StockManager()
    item = db.query(model) if model else None
    if item is None and part_name:
        item = db.query_by_name(part_name)

    if item is None:
        return json.dumps(
            {"available": 0, "location": "", "sufficient": False},
            ensure_ascii=False,
        )

    available = item.quantity - item.reserved
    return json.dumps(
        {
            "available": available,
            "location": item.location,
            "sufficient": available >= quantity,
        },
        ensure_ascii=False,
    )
