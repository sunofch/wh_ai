from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from src.optimization.config import get_optimization_config


class PortDataLoader:
    """CSV data loader migrated from port_inventory_optimization."""

    def __init__(self, target_part: str, pre_fault_window: int = 7, raw_data_dir: str | None = None):
        self.target_part = target_part
        self.pre_fault_window = pre_fault_window
        cfg = get_optimization_config()
        self.raw_data_dir = Path(raw_data_dir) if raw_data_dir else cfg.raw_data_dir
        self.feature_scaler = MinMaxScaler()
        self.target_scaler = MinMaxScaler()

    def load_raw_data(self):
        usage = pd.read_csv(self.raw_data_dir / "spare_part_usage.csv")
        runtime = pd.read_csv(self.raw_data_dir / "equipment_runtime.csv")
        maintenance = pd.read_csv(self.raw_data_dir / "maintenance_orders.csv")
        usage["date"] = pd.to_datetime(usage["date"])
        runtime["date"] = pd.to_datetime(runtime["date"])
        maintenance["date"] = pd.to_datetime(maintenance["date"])
        return usage, runtime, maintenance

    def extract_causal_features(self, usage, runtime, maintenance):
        target_usage = (
            usage[usage["spare_part"] == self.target_part]
            .groupby("date")["quantity_used"]
            .sum()
            .reset_index()
        )
        fault_records = (
            maintenance[maintenance["spare_part"] == self.target_part]
            [["date", "equipment_id"]]
            .drop_duplicates()
            .copy()
        )
        fault_records.rename(columns={"date": "fault_date"}, inplace=True)

        rows = []
        for _, row in fault_records.iterrows():
            for offset in range(1, self.pre_fault_window + 1):
                rows.append({
                    "date": row["fault_date"] - pd.Timedelta(days=offset),
                    "equipment_id": row["equipment_id"],
                })
        pre_fault_df = pd.DataFrame(rows)
        if pre_fault_df.empty:
            return target_usage, pd.DataFrame(columns=[
                "date", "run_hours", "temperature", "vibration", "fault_device_count"
            ])

        causal_runtime = runtime.merge(pre_fault_df, on=["date", "equipment_id"], how="inner")
        daily_health = causal_runtime.groupby("date").agg(
            run_hours=("run_hours", "sum"),
            temperature=("temperature", "mean"),
            vibration=("vibration", "mean"),
            fault_device_count=("equipment_id", "nunique"),
        ).reset_index()
        return target_usage, daily_health

    def prepare_weekly_dataset(self, target_usage, daily_health):
        if target_usage.empty:
            start, end = "2023-01-01", "2025-12-31"
        else:
            start, end = target_usage["date"].min(), target_usage["date"].max()
        all_dates = pd.date_range(start=start, end=end, freq="D")
        df_merged = pd.DataFrame({"date": all_dates})
        df_merged = df_merged.merge(target_usage, on="date", how="left").fillna({"quantity_used": 0})
        df_merged = df_merged.merge(daily_health, on="date", how="left")
        df_merged["run_hours"] = df_merged["run_hours"].fillna(0)
        df_merged["fault_device_count"] = df_merged["fault_device_count"].fillna(0)
        df_merged[["temperature", "vibration"]] = df_merged[["temperature", "vibration"]].ffill().fillna(0)

        df_merged.set_index("date", inplace=True)
        df_weekly = df_merged.resample("W").agg({
            "quantity_used": "sum",
            "run_hours": "sum",
            "temperature": "mean",
            "vibration": "mean",
            "fault_device_count": "sum",
        }).fillna(0)
        df_weekly["week_of_year"] = df_weekly.index.isocalendar().week.astype(float)
        df_weekly["sin_week"] = np.sin(2 * np.pi * df_weekly["week_of_year"] / 52)
        df_weekly["cos_week"] = np.cos(2 * np.pi * df_weekly["week_of_year"] / 52)
        return df_weekly.drop("week_of_year", axis=1)
