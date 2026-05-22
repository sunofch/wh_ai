from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.common.config import config


@dataclass(frozen=True)
class OptimizationRuntimeConfig:
    enabled: bool
    horizon_weeks: int
    lead_time_weeks: int
    safety_stock_weeks: int
    min_restock_qty: int
    max_restock_qty: int
    restock_step_qty: int
    policy: str
    use_lstm: bool
    use_dqn: bool
    model_dir: Path
    raw_data_dir: Path
    processed_data_dir: Path


def get_optimization_config() -> OptimizationRuntimeConfig:
    opt = config.optimization
    return OptimizationRuntimeConfig(
        enabled=opt.enabled,
        horizon_weeks=opt.horizon_weeks,
        lead_time_weeks=opt.lead_time_weeks,
        safety_stock_weeks=opt.safety_stock_weeks,
        min_restock_qty=opt.min_restock_qty,
        max_restock_qty=opt.max_restock_qty,
        restock_step_qty=opt.restock_step_qty,
        policy=opt.policy,
        use_lstm=opt.use_lstm,
        use_dqn=opt.use_dqn,
        model_dir=Path(opt.model_dir),
        raw_data_dir=Path(opt.raw_data_dir),
        processed_data_dir=Path(opt.processed_data_dir),
    )

