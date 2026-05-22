from __future__ import annotations

import json

from langchain_core.tools import tool

from src.optimization.pipeline import analyze_inventory_optimization
from src.warehouse.wms.inventory_db import StockManager


@tool
def analyze_inventory_risk(
    part_name: str,
    model: str = "",
    horizon_weeks: int = 4,
    current_stock: int | None = None,
    forecast: list[int] | None = None,
) -> str:
    """Analyze future inventory risk and recommend a replenishment quantity."""
    available_stock = current_stock
    if available_stock is None:
        item = None
        db = StockManager()
        if model:
            item = db.query(model)
        if item is None and part_name:
            item = db.query_by_name(part_name)
        available_stock = item.available if item is not None else 0

    result = analyze_inventory_optimization(
        part_name=part_name,
        model=model,
        horizon_weeks=horizon_weeks,
        current_stock=available_stock,
        forecast=forecast,
    )
    payload = {"status": "ok", **result.to_dict()}
    return json.dumps(payload, ensure_ascii=False)

