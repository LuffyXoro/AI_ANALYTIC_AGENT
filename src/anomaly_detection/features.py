"""
Feature Engineering

daily x region x category 

RAW features (revenue, orders, profit, ...) turned out to be insufficient on
their own.

Features per (date, region, category):
    revenue, orders, avg_order_value, profit, profit_margin, avg_discount_rate  (raw)
    revenue_ratio, orders_ratio, profit_ratio, discount_ratio  (vs. own group's rolling baseline)

"""

import pandas as pd
import numpy as np

IN_PATH = "data/processed/transactions_with_anomalies.csv"
OUT_PATH = "data/processed/daily_region_category_features.csv"

ROLLING_WINDOW = 30
ROLLING_GAP = 3  # exclude the 3 days immediately before target, same logic as trend_engine.py


def _add_rolling_ratio(group: pd.DataFrame, col: str) -> pd.Series:
    """For each row, ratio of `col` to the trailing ROLLING_WINDOW-day mean of
    `col` for this SAME group, ending ROLLING_GAP days before the row's date."""
    s = group.set_index("order_date")[col].sort_index()
    full_range = pd.date_range(s.index.min(), s.index.max())
    s_full = s.reindex(full_range)

    shifted = s_full.shift(ROLLING_GAP)
    rolling_mean = shifted.rolling(ROLLING_WINDOW, min_periods=5).mean()

    ratio = s_full / rolling_mean
    return ratio.reindex(s.index)  # back to only the dates this group actually has


def build_features(in_path: str = IN_PATH, out_path: str = OUT_PATH) -> pd.DataFrame:
    df = pd.read_csv(in_path, parse_dates=["order_date"])

    grouped = df.groupby(["order_date", "region", "category"]).agg(
        revenue=("sales", "sum"),
        orders=("order_id", "nunique"),
        units_sold=("quantity", "sum"),
        profit=("profit", "sum"),
        avg_discount_rate=("discount", "mean"),
    ).reset_index()

    grouped["avg_order_value"] = grouped["revenue"] / grouped["orders"]
    grouped["profit_margin"] = grouped["profit"] / grouped["revenue"]

    # Relative features: computed per (region, category) group
    ratio_frames = []
    for (region, category), g in grouped.groupby(["region", "category"]):
        g = g.sort_values("order_date").copy()
        g["revenue_ratio"] = _add_rolling_ratio(g, "revenue").values
        g["orders_ratio"] = _add_rolling_ratio(g, "orders").values
        g["profit_ratio"] = _add_rolling_ratio(g, "profit").values
        g["discount_ratio"] = _add_rolling_ratio(g, "avg_discount_rate").values
        ratio_frames.append(g)

    result = pd.concat(ratio_frames, ignore_index=True)

    before = len(result)
    result = result.dropna(subset=["revenue_ratio", "orders_ratio", "profit_ratio", "discount_ratio"])
    print(f"Dropped {before - len(result)} rows with insufficient rolling history")

    result.to_csv(out_path, index=False)
    print(f"Built {len(result):,} feature rows across "
          f"{result['region'].nunique()} regions x {result['category'].nunique()} categories "
          f"-> {out_path}")
    return result


if __name__ == "__main__":
    build_features()