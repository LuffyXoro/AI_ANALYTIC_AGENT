from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np

PERIOD_DAYS = {"dod": 1, "wow": 7, "mom": 30, "yoy": 365}
STABLE_THRESHOLD = 0.05

@dataclass
class TrendResult:
    metric: str; period: str; current_value: float; comparison_value: Optional[float]
    pct_change: Optional[float]; direction: str; baseline_flagged: bool

def daily_series(df, metric, region=None):
    sub = df if region is None else df[df["region"] == region]
    return sub.groupby("order_date")[metric].sum().sort_index()

def _direction(pct_change):
    if pct_change is None: return "insufficient_history"
    if pct_change > STABLE_THRESHOLD: return "increasing"
    if pct_change < -STABLE_THRESHOLD: return "decreasing"
    return "stable"

def detect_trend(df, target_date, metric="sales", period="wow", region=None, baseline_flag_std_threshold=1.5):
    if period not in PERIOD_DAYS:
        raise ValueError(f"period must be one of {list(PERIOD_DAYS)}, got '{period}'")
    series = daily_series(df, metric, region)
    target_date = pd.to_datetime(target_date)
    if target_date not in series.index:
        raise ValueError(f"No data for {target_date} in this slice")
    offset_days = PERIOD_DAYS[period]
    comparison_date = target_date - pd.Timedelta(days=offset_days)
    current_value = series.loc[target_date]
    comparison_value = series.loc[comparison_date] if comparison_date in series.index else None
    pct_change = ((current_value - comparison_value) / comparison_value
                  if comparison_value not in (None, 0) else None)
    baseline_flagged = False
    if comparison_value is not None:
        window_start = comparison_date - pd.Timedelta(days=15)
        window_end = comparison_date + pd.Timedelta(days=15)
        local_window = series.loc[(series.index >= window_start) & (series.index <= window_end) & (series.index != comparison_date)]
        if len(local_window) >= 5:
            local_mean, local_std = local_window.mean(), local_window.std()
            if local_std > 0:
                z = abs(comparison_value - local_mean) / local_std
                baseline_flagged = bool(z > baseline_flag_std_threshold)
    return TrendResult(metric=metric, period=period, current_value=float(current_value),
                        comparison_value=float(comparison_value) if comparison_value is not None else None,
                        pct_change=float(pct_change) if pct_change is not None else None,
                        direction=_direction(pct_change), baseline_flagged=baseline_flagged)