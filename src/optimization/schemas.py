from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class OptimizationResult:
    part_name: str
    model: str = ""
    available_stock: int = 0
    forecast: list[int] | None = None
    forecast_total: int = 0
    lead_time_demand: int = 0
    safety_stock: int = 0
    reorder_point: int = 0
    risk_level: str = "normal"
    recommended_restock_qty: int = 0
    policy: str = "rule"
    report: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["forecast"] = self.forecast or []
        return data

