#!/usr/bin/env python3
"""Lightweight CLI for testing port inventory optimization without vLLM."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.optimization.pipeline import analyze_inventory_optimization


def _parse_forecast(value: str | None) -> list[int] | None:
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return [int(item) for item in items]


def _prompt_if_missing(args: argparse.Namespace) -> argparse.Namespace:
    if args.part_name:
        return args
    print("港口备件库存预测预警测试入口（不依赖 vLLM）", file=sys.stderr)
    args.part_name = input("备件名称: ").strip()
    args.model = input("型号（可选）: ").strip()
    stock_text = input("当前可用库存: ").strip()
    args.current_stock = int(stock_text or "0")
    forecast_text = input("未来周需求预测，逗号分隔（可选，如 10,12,8,15）: ").strip()
    args.forecast = forecast_text or None
    return args


def main() -> int:
    parser = argparse.ArgumentParser(description="Test inventory forecast/warning/replenishment pipeline.")
    parser.add_argument("--part-name", default="", help="备件名称")
    parser.add_argument("--model", default="", help="备件型号")
    parser.add_argument("--current-stock", type=int, default=0, help="当前可用库存")
    parser.add_argument("--forecast", default="", help="逗号分隔的未来周需求预测，例如 10,12,8,15")
    parser.add_argument("--horizon-weeks", type=int, default=4, help="预测周期（周）")
    args = _prompt_if_missing(parser.parse_args())

    result = analyze_inventory_optimization(
        part_name=args.part_name,
        model=args.model,
        horizon_weeks=args.horizon_weeks,
        current_stock=args.current_stock,
        forecast=_parse_forecast(args.forecast),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
