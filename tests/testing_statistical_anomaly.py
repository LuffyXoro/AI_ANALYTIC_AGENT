"""
    python -m pytest tests/test_statistical_anomaly.py -v
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.anomaly_detection.statistics import (
    detect_zscore_global,
    detect_period_average,
)
@pytest.fixture
def flat_series_with_dip():
    dates = pd.date_range("2023-01-01", periods=20)

    rng = np.random.default_rng(1)

    baseline_vals = 1000 + rng.normal(0, 5, size=16)
    dip_vals = [400.0] * 4

    values = (
        list(baseline_vals[:9])
        + dip_vals
        + list(baseline_vals[9:])
    )

    return pd.Series(values, index=dates)


def test_zscore_global_flags_the_obvious_dip(flat_series_with_dip):

    result = detect_zscore_global(
        flat_series_with_dip,
        threshold=1.5,
    )

    dip_days = flat_series_with_dip.index[9:13]

    assert result.loc[dip_days, "is_anomaly"].all()


def test_period_average_detects_known_dip(flat_series_with_dip):

    result = detect_period_average(
        flat_series_with_dip,
        period_start=flat_series_with_dip.index[9],
        period_end=flat_series_with_dip.index[12],
        threshold=2.0,
    )

    assert result["is_anomaly"] is True
    assert result["window_mean"] == pytest.approx(400.0)


def test_period_average_no_anomaly_on_flat_series():
    dates = pd.date_range("2023-01-01", periods=40)

    rng = np.random.default_rng(2)

    values = 1000 + rng.normal(0, 20, size=40)

    series = pd.Series(values, index=dates)

    result = detect_period_average(
        series,
        period_start=dates[15],
        period_end=dates[18],
        threshold=2.0,
    )

    assert result["is_anomaly"] is False


def test_regression_scenario1_strongly_detected():
   

    df = pd.read_csv(
        "data/processed/transactions_with_anomalies.csv",
        parse_dates=["order_date"],
    )

    south = df[df["region"] == "South"]

    series = (
        south.groupby("order_date")["sales"]
        .sum()
        .sort_index()
    )

    series.index = pd.to_datetime(series.index)

    result = detect_period_average(
        series,
        "2022-06-01",
        "2022-06-14",
        threshold=2.0,
    )

    assert result["z_score"] < -4.0
    assert result["is_anomaly"] is True


def test_regression_scenario2_detected_at_correct_dimension():
    

    df = pd.read_csv(
        "data/processed/transactions_with_anomalies.csv",
        parse_dates=["order_date"],
    )

    
    correct = df[
        (df["region"] == "North")
        & (df["category"] == "Furniture")
    ]

    correct_series = (
        correct.groupby("order_date")["profit"]
        .sum()
        .sort_index()
    )

    correct_series.index = pd.to_datetime(correct_series.index)

    correct_result = detect_period_average(
        correct_series,
        "2021-09-01",
        "2021-09-14",
        threshold=2.0,
    )

    assert correct_result["is_anomaly"] is True

    

    coarse = df[df["region"] == "North"]

    coarse_series = (
        coarse.groupby("order_date")["profit"]
        .sum()
        .sort_index()
    )

    coarse_series.index = pd.to_datetime(coarse_series.index)

    coarse_result = detect_period_average(
        coarse_series,
        "2021-09-01",
        "2021-09-14",
        threshold=2.0,
    )

    assert coarse_result["is_anomaly"] is False


def test_regression_scenario3_correctly_not_flagged():

    df = pd.read_csv(
        "data/processed/transactions_with_anomalies.csv",
        parse_dates=["order_date"],
    )

    sub = df[
        (df["region"] == "West")
        & (df["category"] == "Household Items")
    ]

    series = (
        sub.groupby("order_date")["sales"]
        .sum()
        .sort_index()
    )

    series.index = pd.to_datetime(series.index)

    result = detect_period_average(
        series,
        "2023-03-01",
        "2023-03-14",
        threshold=2.0,
    )

    assert result["is_anomaly"] is False

    assert -2.5 < result["z_score"] < -0.5