from __future__ import annotations

from statistics import mean


def fallback_forecast_from_history(
    history: list[int] | None,
    horizon_weeks: int,
    default_weekly_demand: int = 10,
) -> list[int]:
    """Build a deterministic fallback forecast when trained models are unavailable."""
    if horizon_weeks <= 0:
        return []
    values = [int(v) for v in (history or []) if v is not None and int(v) >= 0]
    if not values:
        return [default_weekly_demand] * horizon_weeks
    weekly = max(0, int(round(mean(values[-min(len(values), 8):]))))
    return [weekly] * horizon_weeks

