"""
// core dimension-contribution math //

"Revenue in [scope] fell by X during [window].
Which value of [dimension] (region, category, ...) is responsible, and how
much?"

Compare its metric total during the
anomaly window against its own EXPECTED value 

Dimension value can
only be blamed for its own shortfall relatie to ITS OWN normal behavior,
not relative to the scope's average 
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd

ROLLING_WINDOW = 30
ROLLING_GAP = 3


@dataclass
class Contribution:
    dimension_value: str
    actual: float
    expected: float
    deviation: float          # actual - expected
    pct_of_scope_deviation: float  
    own_pct_change: float     # (actual - expected) / expected


def _expected_value(df: pd.DataFrame, metric: str, window_start: str, window_end: str,
                     extra_filter: Optional[pd.Series] = None) -> float:
    sub = df if extra_filter is None else df[extra_filter]
    daily = sub.groupby("order_date")[metric].sum()

    baseline_end = pd.Timestamp(window_start) - pd.Timedelta(days=ROLLING_GAP)
    baseline_start = baseline_end - pd.Timedelta(days=ROLLING_WINDOW)
    baseline = daily[(daily.index >= baseline_start) & (daily.index < baseline_end)]

    n_window_days = (pd.Timestamp(window_end) - pd.Timestamp(window_start)).days + 1
    daily_rate = baseline.mean() if len(baseline) > 0 else 0.0
    return daily_rate * n_window_days


def contribution_analysis(
    df: pd.DataFrame,
    metric: str,
    dimension: str,
    window_start: str,
    window_end: str,
    scope_filter: Optional[dict] = None,
) -> pd.DataFrame:
    scope_mask = pd.Series(True, index=df.index)
    if scope_filter:
        for col, val in scope_filter.items():
            scope_mask &= df[col] == val

    scope_df = df[scope_mask]
    scope_actual = scope_df[scope_df["order_date"].between(window_start, window_end)][metric].sum()
    scope_expected = _expected_value(df, metric, window_start, window_end, extra_filter=scope_mask)
    
    rows = []
    for value in scope_df[dimension].dropna().unique():
        value_mask = scope_mask & (df[dimension] == value)
        value_df = df[value_mask]
        actual = value_df[value_df["order_date"].between(window_start, window_end)][metric].sum()
        expected = _expected_value(df, metric, window_start, window_end, extra_filter=value_mask)
        deviation = actual - expected

        rows.append(dict(dimension_value=value, actual=actual, expected=expected, deviation=deviation))

    sum_of_deviations = sum(r["deviation"] for r in rows)

    for r in rows:
        r["pct_of_scope_deviation"] = (
            r["deviation"] / sum_of_deviations * 100 if sum_of_deviations != 0 else 0.0
        )
        r["own_pct_change"] = (r["deviation"] / r["expected"] * 100) if r["expected"] else 0.0

    result = pd.DataFrame(rows)
    result.attrs["scope_actual"] = scope_actual
    result.attrs["scope_expected_independent_estimate"] = scope_expected
    result.attrs["scope_deviation_sum_of_parts"] = sum_of_deviations
    return result.sort_values("deviation", key=abs, ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    df = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])

    print("=== Company-wide revenue deviation, broken down by region ===")
    print("(Testing Scenario 1: 2022-06-01 to 06-14, expect South to dominate)")
    result = contribution_analysis(
        df, metric="sales", dimension="region",
        window_start="2022-06-01", window_end="2022-06-14",
    )
    print(result.round(2))