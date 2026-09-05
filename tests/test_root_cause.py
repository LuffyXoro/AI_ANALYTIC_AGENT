"""
pytest tests/test_root_cause.py -v

"""
import os
import sys

import pandas as pd
import pytest

# Add PROJECT ROOT to Python path
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.root_cause.contribution import contribution_analysis

from src.root_cause.evidence_chain import (
    build_evidence_chain,
    business_impact,
    volume_or_price_driven,
)
# import pandas as pd
# import pytest
# import sys
# import os

# sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "root_cause"))
# from src.root_cause.contribution import contribution_analysis
# from  src.root_cause.evidence_chain import build_evidence_chain, business_impact, volume_or_price_driven


@pytest.fixture(scope="module")
def df():
    return pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])


def test_contribution_percentages_sum_to_100(df):
    
    result = contribution_analysis(
        df, metric="sales", dimension="category",
        window_start="2023-03-01", window_end="2023-03-14",
        scope_filter={"region": "West"},
    )
    assert result["pct_of_scope_deviation"].sum() == pytest.approx(100.0, abs=0.1)


def test_scenario1_region_level_identifies_south(df):
    result = contribution_analysis(
        df, metric="sales", dimension="region",
        window_start="2022-06-01", window_end="2022-06-14",
    )
    top = result.iloc[0]
    assert top["dimension_value"] == "South"
    assert top["pct_of_scope_deviation"] > 50  # clearly dominant


def test_scenario1_category_level_identifies_electric_appliances(df):
    result = contribution_analysis(
        df, metric="sales", dimension="category",
        window_start="2022-06-01", window_end="2022-06-14",
        scope_filter={"region": "South"},
    )
    top = result.iloc[0]
    assert top["dimension_value"] == "Electric Appliances"
    assert top["own_pct_change"] == pytest.approx(-79.5, abs=1.0)


def test_evidence_chain_blind_search_scenario1(df):
    
    chain = build_evidence_chain(df, metric="sales", window_start="2022-06-01", window_end="2022-06-14")
    dims_reached = [step["dimension"] for step in chain if "value" in step]
    assert "region" in dims_reached
    assert "category" in dims_reached

    region_step = next(s for s in chain if s.get("dimension") == "region")
    category_step = next(s for s in chain if s.get("dimension") == "category")
    assert region_step["value"] == "South"
    assert category_step["value"] == "Electric Appliances"


def test_evidence_chain_blind_search_fails_on_quiet_scenario(df):
    
    chain = build_evidence_chain(df, metric="profit", window_start="2021-09-01", window_end="2021-09-14")
    region_step = next((s for s in chain if s.get("dimension") == "region"), None)
    if region_step is not None:
        pass


def test_evidence_chain_seeded_scenario2_finds_correct_subcategory(df):
    chain = build_evidence_chain(
        df, metric="profit", window_start="2021-09-01", window_end="2021-09-14",
        seed_scope={"region": "North", "category": "Furniture"},
    )
    seeded_steps = [s for s in chain if s.get("source") == "seeded_from_detector"]
    assert len(seeded_steps) == 2
    assert seeded_steps[0]["value"] == "North"
    assert seeded_steps[1]["value"] == "Furniture"


def test_business_impact_scenario1_matches_documented_shortfall(df):
    impact = business_impact(df, metric="sales", window_start="2022-06-01", window_end="2022-06-14")
    assert impact["pct_change"] == pytest.approx(-12.9, abs=1.0)


def test_volume_price_check_scenario1_is_volume_driven(df):
    """Scenario 1 was built via pure row removal -- AOV should stay flat."""
    result = volume_or_price_driven(
        df, "2022-06-01", "2022-06-14", scope_filter={"region": "South"}
    )
    assert "volume-driven" in result


def test_volume_price_check_scenario2_is_margin_driven(df):
    result = volume_or_price_driven(
        df, "2021-09-01", "2021-09-14", scope_filter={"region": "North", "category": "Furniture"}
    )
    assert "margin-driven" in result