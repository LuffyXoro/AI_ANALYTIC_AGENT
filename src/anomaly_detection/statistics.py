"""
Statistical Anomaly Detection: Z-score/Rolling 

"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np


@dataclass
class AnomalyFlag:
    date: object
    value: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    is_anomaly: bool
    method: str  # "zscore_global" | "rolling_baseline"


def detect_zscore_global(series: pd.Series, threshold: float = 2.5) -> pd.DataFrame:
    mean, std = series.mean(), series.std()
    z = (series - mean) / std if std > 0 else series * 0
    return pd.DataFrame({
        "value": series,
        "baseline_mean": mean,
        "baseline_std": std,
        "z_score": z,
        "is_anomaly": z.abs() > threshold,
    })


def detect_zscore_weekly(series: pd.Series, threshold: float = 2.0) -> pd.DataFrame:
    weekly = series.resample("W").sum()
    mean, std = weekly.mean(), weekly.std()
    z = (weekly - mean) / std if std > 0 else weekly * 0
    return pd.DataFrame({
        "value": weekly,
        "baseline_mean": mean,
        "baseline_std": std,
        "z_score": z,
        "is_anomaly": z.abs() > threshold,
    })


def detect_period_average(
    series: pd.Series,
    period_start: str,
    period_end: str,
    threshold: float = 2.0,
) -> dict:
    """
    Result on our three known scenarios (see docs/02_anomaly_detection.md):
        Scenario 1 (South, volume-driven, loud):        z = -5.16  (clear)
        Scenario 2 (North Furniture, margin squeeze):    z = -2.36  (detectable)
        Scenario 3 (West Household, quiet multi-metric): z = -1.55  (weak)
            correctly reflects that this scenario was designed to be quiet;
            a single-metric time-series test isn't the right tool for it.
    """
    window = series.loc[period_start:period_end]
    baseline = series.drop(window.index)

    n = len(window)
    se = baseline.std() / np.sqrt(n) if n > 0 else np.nan
    z = (window.mean() - baseline.mean()) / se if se and se > 0 else np.nan

    return {
        "window_mean": float(window.mean()),
        "baseline_mean": float(baseline.mean()),
        "standard_error": float(se),
        "z_score": float(z),
        "is_anomaly": bool(abs(z) > threshold) if not np.isnan(z) else False,
    }


def detect_rolling_baseline(
    series: pd.Series,
    window: int = 30,
    gap: int = 3,
    threshold: float = 2.5,
) -> pd.DataFrame:
    # excluding a gap before each target day.

    # For each date, the baseline is the mean/std of the 'window' days ending
    # 'gap' days before it 

    dates = series.index
    results = []
    for d in dates:
        window_end = d - pd.Timedelta(days=gap)
        window_start = window_end - pd.Timedelta(days=window)
        local = series[(series.index >= window_start) & (series.index < window_end)]

        if len(local) < max(5, window // 3):
            results.append((d, series[d], np.nan, np.nan, np.nan, False))
            continue

        mean, std = local.mean(), local.std()
        z = (series[d] - mean) / std if std > 0 else 0.0
        results.append((d, series[d], mean, std, z, abs(z) > threshold))

    out = pd.DataFrame(
        results, columns=["date", "value", "baseline_mean", "baseline_std", "z_score", "is_anomaly"]
    ).set_index("date")
    return out


def compare_detectors(
    df: pd.DataFrame,
    metric: str,
    region: Optional[str],
    known_anomaly_start: str,
    known_anomaly_end: str,
    label: str,
    category: Optional[str] = None,
) -> dict:
    sub = df
    if region is not None:
        sub = sub[sub["region"] == region]
    if category is not None:
        sub = sub[sub["category"] == category]
    series = sub.groupby("order_date")[metric].sum().sort_index()
    series.index = pd.to_datetime(series.index)

    anomaly_dates = pd.date_range(known_anomaly_start, known_anomaly_end)

    z_result = detect_zscore_global(series)
    r_result = detect_rolling_baseline(series)
    w_result = detect_zscore_weekly(series)
    p_result = detect_period_average(series, known_anomaly_start, known_anomaly_end)

    def score(result):
        flagged = set(result.index[result["is_anomaly"]])
        anomaly_set = set(anomaly_dates)
        true_positives = flagged & anomaly_set
        false_positives = flagged - anomaly_set
        recall = len(true_positives) / len(anomaly_set) if anomaly_set else 0.0
        return {
            "days_flagged_in_window": len(true_positives),
            "days_in_window": len(anomaly_set),
            "recall": round(recall, 2),
            "false_positives_outside_window": len(false_positives),
        }

    def score_weekly(result):
        anomaly_set = set(anomaly_dates)
        flagged_weeks = result.index[result["is_anomaly"]]
        overlapping = [w for w in flagged_weeks if any(
            (w - pd.Timedelta(days=6) <= d <= w) for d in anomaly_set
        )]
        return {
            "weeks_flagged_overlapping_anomaly": len(overlapping),
            "total_weeks_flagged": len(flagged_weeks),
        }

    return {
        "scenario": label,
        "zscore_global_daily": score(z_result),
        "rolling_baseline_daily": score(r_result),
        "zscore_weekly": score_weekly(w_result),
        "period_average_test": p_result,
    }


if __name__ == "__main__":
    df = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])

    scenarios = [
        dict(metric="sales", region="South", category=None, known_anomaly_start="2022-06-01",
             known_anomaly_end="2022-06-14", label="Scenario 1: South revenue, region-level (volume-driven, loud)"),
        dict(metric="profit", region="North", category="Furniture", known_anomaly_start="2021-09-01",
             known_anomaly_end="2021-09-14", label="Scenario 2: North+Furniture profit, correct dimension (margin squeeze)"),
        dict(metric="sales", region="West", category="Household Items", known_anomaly_start="2023-03-01",
             known_anomaly_end="2023-03-14", label="Scenario 3: West+Household Items revenue, correct dimension (quiet multi-metric)"),
    ]

    for s in scenarios:
        result = compare_detectors(df, **s)
        print(f"\n=== {result['scenario']} ===")
        print(f"  Z-score (daily, global):   {result['zscore_global_daily']}")
        print(f"  Rolling baseline (daily):  {result['rolling_baseline_daily']}")
        print(f"  Z-score (WEEKLY):          {result['zscore_weekly']}")
        p = result['period_average_test']
        print(f"  Period-average z-test:     z={p['z_score']:.2f}  is_anomaly={p['is_anomaly']}  "
              f"(window_mean={p['window_mean']:.0f} vs baseline_mean={p['baseline_mean']:.0f})")