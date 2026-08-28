''' AI AGENT '''

from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np


PERIOD_DAYS = {"dod": 1, "wow": 7, "mom": 30, "yoy": 365}
STABLE_THRESHOLD = 0.05


@dataclass
class TrendResult:
    metric: str
    period: str          # "dod" | "wow" | "mom" | "yoy"
    current_value: float
    comparison_value: Optional[float]
    pct_change: Optional[float]
    direction: str        # "increasing" | "decreasing" | "stable" | "insufficient_history"
    baseline_flagged: bool  # True if the comparison period itself looks anomalous


def daily_series(df: pd.DataFrame, metric: str, region: Optional[str] = None) -> pd.Series:
    """Build a daily total for one metric, optionally scoped to one region."""
    sub = df if region is None else df[df["region"] == region]
    return sub.groupby("order_date")[metric].sum().sort_index()


def _direction(pct_change: Optional[float]) -> str:
    if pct_change is None:
        return "insufficient_history"
    if pct_change > STABLE_THRESHOLD:
        return "increasing"
    if pct_change < -STABLE_THRESHOLD:
        return "decreasing"
    return "stable"


def detect_trend(
    df: pd.DataFrame,
    target_date,
    metric: str = "sales",
    period: str = "wow",
    region: Optional[str] = None,
    baseline_flag_std_threshold: float = 1.5,
) -> TrendResult:
    """
    Comparing `metric` on `target_date` against the same metric N days earlier
    (N determined by `period`: dod=1, wow=7, mom=30, yoy=365).

    baseline_flagged: True when the COMPARISON day itself deviates from the
    surrounding 30-day local average by more than `baseline_flag_std_threshold`
    standard deviations. This is what catches the "+253%" false-growth trap --
    it doesn't fix the number, but it tells the caller not to trust it blindly.
    """
    if period not in PERIOD_DAYS:
        raise ValueError(f"period must be one of {list(PERIOD_DAYS)}, got '{period}'")

    series = daily_series(df, metric, region)
    target_date = pd.to_datetime(target_date).date()

    if target_date not in series.index:
        raise ValueError(f"No data for {target_date} in this slice")

    offset_days = PERIOD_DAYS[period]
    comparison_date = target_date - pd.Timedelta(days=offset_days)

    current_value = series.loc[target_date]
    comparison_value = series.loc[comparison_date] if comparison_date in series.index else None

    pct_change = (
        (current_value - comparison_value) / comparison_value
        if comparison_value not in (None, 0)
        else None
    )

    baseline_flagged = False
    if comparison_value is not None:
        # Look at the 30 days around the comparison date (excluding it) to see
        # whether the comparison point itself was unusual.
        window_start = comparison_date - pd.Timedelta(days=15)
        window_end = comparison_date + pd.Timedelta(days=15)
        local_window = series.loc[
            (series.index >= window_start) & (series.index <= window_end) & (series.index != comparison_date)
        ]
        if len(local_window) >= 5:
            local_mean, local_std = local_window.mean(), local_window.std()
            if local_std > 0:
                z = abs(comparison_value - local_mean) / local_std
                baseline_flagged = bool(z > baseline_flag_std_threshold)

    return TrendResult(
        metric=metric,
        period=period,
        current_value=float(current_value),
        comparison_value=float(comparison_value) if comparison_value is not None else None,
        pct_change=float(pct_change) if pct_change is not None else None,
        direction=_direction(pct_change),
        baseline_flagged=baseline_flagged,
    )
x

if __name__ == "__main__":
    df = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])
    df["order_date"] = df["order_date"].dt.date

    print("WoW trend, South region, across the Scenario 1 anomaly window")
    for day in pd.date_range("2022-06-01", "2022-06-14"):
        r = detect_trend(df, day, metric="sales", period="wow", region="South")
        flag = "  <-- BASELINE ITSELF LOOKS ANOMALOUS, interpret with caution" if r.baseline_flagged else ""
        pct = f"{r.pct_change*100:+.1f}%" if r.pct_change is not None else "n/a"
        print(f"{day.date()}  wow_change={pct:>8}  direction={r.direction:<10}{flag}")

