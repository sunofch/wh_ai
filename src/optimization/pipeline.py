from __future__ import annotations

from src.optimization.config import get_optimization_config
from src.optimization.data_adapter import fallback_forecast_from_history
from src.optimization.schemas import OptimizationResult
from src.optimization.warning import classify_inventory_risk, round_restock_quantity


def analyze_inventory_optimization(
    part_name: str,
    model: str | None = None,
    horizon_weeks: int | None = None,
    current_stock: int | None = None,
    forecast: list[int] | None = None,
    demand_history: list[int] | None = None,
) -> OptimizationResult:
    """Analyze demand risk and produce a replenishment recommendation.

    The first integrated version uses deterministic policy by default. LSTM/DQN
    modules are kept as optional backends controlled by configuration.
    """
    cfg = get_optimization_config()
    horizon = horizon_weeks or cfg.horizon_weeks
    available_stock = max(0, int(current_stock or 0))
    demand_forecast = [max(0, int(v)) for v in (forecast or [])]
    if not demand_forecast:
        demand_forecast = fallback_forecast_from_history(demand_history, horizon)
    demand_forecast = demand_forecast[:horizon]
    if len(demand_forecast) < horizon:
        demand_forecast.extend([0] * (horizon - len(demand_forecast)))

    forecast_total = sum(demand_forecast)
    lead_time = max(1, cfg.lead_time_weeks)
    lead_time_demand = sum(demand_forecast[:lead_time])
    safety_weeks = max(1, cfg.safety_stock_weeks)
    weekly_avg = int(round(forecast_total / max(1, len(demand_forecast))))
    safety_stock = max(weekly_avg * safety_weeks, weekly_avg)
    reorder_point = lead_time_demand + safety_stock
    risk_level = classify_inventory_risk(available_stock, lead_time_demand, reorder_point)

    raw_restock = 0
    if risk_level != "normal":
        target_stock = forecast_total + safety_stock
        raw_restock = target_stock - available_stock
    recommended_qty = round_restock_quantity(
        raw_restock,
        cfg.min_restock_qty,
        cfg.max_restock_qty,
        cfg.restock_step_qty,
    )

    name = part_name or model or "未知备件"
    report = (
        f"{name}未来{len(demand_forecast)}周预测需求为{forecast_total}件，"
        f"当前可用库存{available_stock}件，动态补货点为{reorder_point}件，"
        f"风险等级为{risk_level}，建议补货{recommended_qty}件。"
    )
    return OptimizationResult(
        part_name=part_name,
        model=model or "",
        available_stock=available_stock,
        forecast=demand_forecast,
        forecast_total=forecast_total,
        lead_time_demand=lead_time_demand,
        safety_stock=safety_stock,
        reorder_point=reorder_point,
        risk_level=risk_level,
        recommended_restock_qty=recommended_qty,
        policy=cfg.policy,
        report=report,
    )

