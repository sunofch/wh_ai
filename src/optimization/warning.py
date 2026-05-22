from __future__ import annotations


def classify_inventory_risk(available_stock: int, lead_time_demand: int, reorder_point: int) -> str:
    """Classify stockout risk from deterministic inventory thresholds."""
    if available_stock <= lead_time_demand:
        return "critical"
    if available_stock <= reorder_point:
        return "warning"
    return "normal"


def round_restock_quantity(quantity: int, min_qty: int, max_qty: int, step_qty: int) -> int:
    """Clamp and round a replenishment quantity to the configured order step."""
    if quantity <= 0:
        return 0
    quantity = max(min_qty, min(quantity, max_qty))
    if step_qty <= 1:
        return quantity
    return ((quantity + step_qty - 1) // step_qty) * step_qty

