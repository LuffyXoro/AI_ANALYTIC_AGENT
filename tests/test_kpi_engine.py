#  python -m pytest tests/test_kpi_engine.py -v

import pandas as pd
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from src.analytics.kpi_engine import compute_kpis, kpis_by_dimension, filter_transactions


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "order_id": ["A1", "A2", "A3", "A4"],
        "order_date": pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-02", "2023-01-03"]).date,
        "sales": [100.0, 200.0, 300.0, 400.0],
        "quantity": [1, 2, 3, 4],
        "discount": [0.1, 0.2, 0.1, 0.3],
        "profit": [10.0, 20.0, 45.0, 40.0],
        "region": ["East", "East", "West", "West"],
        "category": ["A", "B", "A", "B"],
    })


def test_compute_kpis_basic(sample_df):
    kpis = compute_kpis(sample_df)
    assert kpis.revenue == 1000.0
    assert kpis.orders == 4
    assert kpis.units_sold == 10
    assert kpis.avg_order_value == 250.0
    assert kpis.profit == 115.0
    assert kpis.profit_margin == pytest.approx(0.115)
    assert kpis.avg_discount_rate == pytest.approx(0.175)


def test_compute_kpis_empty_raises():
    empty = pd.DataFrame(columns=["order_id", "sales", "quantity", "discount", "profit"])
    with pytest.raises(ValueError):
        compute_kpis(empty)


def test_filter_transactions_by_region(sample_df):
    east_only = filter_transactions(sample_df, region="East")
    assert len(east_only) == 2
    assert set(east_only["region"]) == {"East"}


def test_filter_transactions_by_date_range(sample_df):
    filtered = filter_transactions(sample_df, start_date="2023-01-02", end_date="2023-01-02")
    assert len(filtered) == 2


def test_kpis_by_dimension_region(sample_df):
    result = kpis_by_dimension(sample_df, "region")
    assert set(result.index) == {"East", "West"}
    assert result.loc["East", "revenue"] == 300.0
    assert result.loc["West", "revenue"] == 700.0


def test_kpis_by_dimension_invalid_column(sample_df):
    with pytest.raises(ValueError):
        kpis_by_dimension(sample_df, "not_a_real_column")


def test_regression_scenario2_margin_squeeze_result():
    """
    Regression test locking in the verified result of Scenario 2
    (North Furniture profit-margin squeeze) from
    docs/01_anomaly_simulation.md, so a future refactor of the KPI engine
    can't silently break the numbers our anomaly narrative depends on.
    """
    df = pd.read_csv(
        "data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"]
    )
    df["order_date"] = df["order_date"].dt.date

    sliced = filter_transactions(
        df, start_date="2021-09-01", end_date="2021-09-14", region="North"
    )
    sliced = sliced[sliced["category"] == "Furniture"]
    kpis = compute_kpis(sliced)

    assert kpis.revenue == pytest.approx(722140, abs=1)
    assert kpis.profit == pytest.approx(65541, abs=1)
    assert kpis.avg_discount_rate == pytest.approx(0.60, abs=0.01)

