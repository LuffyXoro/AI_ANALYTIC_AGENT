"""
sanity-checking the daily ratio features showed real directional signal (anomaly rows average
ratio 0.77 vs 1.02 for normal) but massive overlap -- the "normal"
distribution itself ranges from 0.0015 to 5.6x its own baseline day to day.

"""

import pandas as pd

IN_PATH = "data/processed/transactions_with_anomalies.csv"
OUT_PATH = "data/processed/weekly_region_category_features.csv"

ROLLING_WEEKS = 8
ROLLING_GAP_WEEKS = 1


def _rolling_ratio(s: pd.Series, window: int, gap: int) -> pd.Series:
    shifted = s.shift(gap)
    rolling_mean = shifted.rolling(window, min_periods=4).mean()
    return s / rolling_mean


def build_weekly_features(in_path: str = IN_PATH, out_path: str = OUT_PATH) -> pd.DataFrame:
    df = pd.read_csv(in_path, parse_dates=["order_date"])
    df["week"] = df["order_date"].dt.to_period("W").dt.start_time

    grouped = df.groupby(["week", "region", "category"]).agg(
        revenue=("sales", "sum"),
        orders=("order_id", "nunique"),
        profit=("profit", "sum"),
        avg_discount_rate=("discount", "mean"),
    ).reset_index()

    grouped["avg_order_value"] = grouped["revenue"] / grouped["orders"]
    grouped["profit_margin"] = grouped["profit"] / grouped["revenue"]

    ratio_frames = []
    for (region, category), g in grouped.groupby(["region", "category"]):
        g = g.sort_values("week").copy()
        full_weeks = pd.date_range(g["week"].min(), g["week"].max(), freq="W-MON")
        g_full = g.set_index("week").reindex(full_weeks)

        g_full["revenue_ratio"] = _rolling_ratio(g_full["revenue"], ROLLING_WEEKS, ROLLING_GAP_WEEKS)
        g_full["orders_ratio"] = _rolling_ratio(g_full["orders"], ROLLING_WEEKS, ROLLING_GAP_WEEKS)
        g_full["profit_ratio"] = _rolling_ratio(g_full["profit"], ROLLING_WEEKS, ROLLING_GAP_WEEKS)
        g_full["discount_ratio"] = _rolling_ratio(g_full["avg_discount_rate"], ROLLING_WEEKS, ROLLING_GAP_WEEKS)

        g_full["region"], g_full["category"] = region, category
        ratio_frames.append(g_full.dropna(subset=["revenue"]).reset_index().rename(columns={"index": "week"}))

    result = pd.concat(ratio_frames, ignore_index=True)
    before = len(result)
    result = result.dropna(subset=["revenue_ratio", "orders_ratio", "profit_ratio", "discount_ratio"])
    print(f"Dropped {before - len(result)} weeks with insufficient rolling history")

    result.to_csv(out_path, index=False)
    print(f"Built {len(result):,} weekly feature rows -> {out_path}")
    return result


if __name__ == "__main__":
    build_weekly_features()