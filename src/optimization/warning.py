from __future__ import annotations

from datetime import date


def weeks_until_expiry(
    inbound_date: str,
    expected_life_weeks: int,
    today: date | None = None,
) -> float | None:
    """Remaining life in weeks; None when lifecycle data is missing/invalid."""
    if not inbound_date or expected_life_weeks <= 0:
        return None
    try:
        inbound = date.fromisoformat(inbound_date[:10])
    except ValueError:
        return None
    today = today or date.today()
    elapsed_weeks = (today - inbound).days / 7
    return expected_life_weeks - elapsed_weeks


def classify_life_risk(
    inbound_date: str,
    expected_life_weeks: int,
    today: date | None = None,
    warn_weeks: int = 2,
) -> str:
    """Classify spare-part life expiry risk: expired / expiring / ok / unknown."""
    remaining = weeks_until_expiry(inbound_date, expected_life_weeks, today)
    if remaining is None:
        return "unknown"
    if remaining <= 0:
        return "expired"
    if remaining <= warn_weeks:
        return "expiring"
    return "ok"


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

