"""
Evidence Chain + Business Impact


    Revenue anomaly -> Region -> Category -> AOV

At each level, contribution_analysis() finds the top contributor; we recurse
into it until we run out of dimensions to check or the top contributor no
longer explains a meaningful share of the deviation.
"""

from typing import List, Optional
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from contribution import contribution_analysis

DRILL_ORDER = ["region", "state", "category", "sub_category"]
MIN_EXPLAINED_SHARE = 30.0  # stop drilling if top contributor explains less than this


def business_impact(df: pd.DataFrame, metric: str, window_start: str, window_end: str,
                     scope_filter: Optional[dict] = None) -> dict:
    """Expected vs actual for `metric`, in currency -- the '₹3.5L shortfall' number."""
    from contribution import _expected_value
    mask = pd.Series(True, index=df.index)
    if scope_filter:
        for col, val in scope_filter.items():
            mask &= df[col] == val
    sub = df[mask]
    actual = sub[sub["order_date"].between(window_start, window_end)][metric].sum()
    expected = _expected_value(df, metric, window_start, window_end, extra_filter=mask)
    return {
        "metric": metric, "actual": round(actual, 2), "expected": round(expected, 2),
        "shortfall": round(expected - actual, 2), "pct_change": round((actual-expected)/expected*100, 2) if expected else None,
    }


def build_evidence_chain(
    df: pd.DataFrame,
    metric: str,
    window_start: str,
    window_end: str,
    seed_scope: Optional[dict] = None,
) -> List[dict]:
    
    chain = []
    scope_filter = dict(seed_scope) if seed_scope else {}
    remaining_dims = [d for d in DRILL_ORDER if d not in scope_filter]

    if seed_scope:
        for dim, val in seed_scope.items():
            chain.append({"dimension": dim, "value": val, "source": "seeded_from_detector"})

    while remaining_dims:
        best_dim, best_result, best_top = None, None, None

        for dimension in remaining_dims:
            result = contribution_analysis(df, metric, dimension, window_start, window_end, scope_filter or None)
            if result.empty:
                continue
            top = result.iloc[0]
            if best_top is None or abs(top["pct_of_scope_deviation"]) > abs(best_top["pct_of_scope_deviation"]):
                best_dim, best_result, best_top = dimension, result, top

        remaining_dims.remove(best_dim) if best_dim else None

        if best_top is None or abs(best_top["pct_of_scope_deviation"]) < MIN_EXPLAINED_SHARE:
            chain.append({"stopped_reason":
                          f"no remaining dimension explains >= {MIN_EXPLAINED_SHARE}% of the deviation"})
            break

        chain.append({
            "dimension": best_dim,
            "value": best_top["dimension_value"],
            "pct_of_scope_deviation": round(best_top["pct_of_scope_deviation"], 1),
            "own_pct_change": round(best_top["own_pct_change"], 1),
        })
        scope_filter[best_dim] = best_top["dimension_value"]

    return chain


def volume_or_price_driven(df: pd.DataFrame, window_start: str, window_end: str, scope_filter: dict) -> str:
   
    mask = pd.Series(True, index=df.index)
    for col, val in scope_filter.items():
        mask &= df[col] == val
    sub = df[mask]

    window = sub[sub["order_date"].between(window_start, window_end)]
    baseline = sub[~sub["order_date"].between(window_start, window_end)]

    window_aov = window["sales"].sum() / window["order_id"].nunique() if len(window) else 0
    baseline_aov = baseline["sales"].sum() / baseline["order_id"].nunique() if len(baseline) else 0
    aov_pct_change = (window_aov - baseline_aov) / baseline_aov * 100 if baseline_aov else 0

    window_discount = window["discount"].mean() if len(window) else 0
    baseline_discount = baseline["discount"].mean() if len(baseline) else 0
    discount_pct_change = (
        (window_discount - baseline_discount) / baseline_discount * 100 if baseline_discount else 0
    )

    aov_moved = abs(aov_pct_change) >= 10
    discount_moved = abs(discount_pct_change) >= 15

    if discount_moved and not aov_moved:
        return f"margin-driven (discount rate changed {discount_pct_change:+.1f}%, AOV flat at {aov_pct_change:+.1f}%)"
    if aov_moved:
        return f"price-driven (AOV changed {aov_pct_change:+.1f}%)"
    return f"volume-driven (AOV changed only {aov_pct_change:+.1f}%, discount changed {discount_pct_change:+.1f}%)"


if __name__ == "__main__":
    df = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])

    scenarios = [
        ("Scenario 1 (loud, blind top-down search)", "sales", "2022-06-01", "2022-06-14", None),
        ("Scenario 2 (quiet, seeded from detector: North+Furniture)", "profit", "2021-09-01", "2021-09-14",
         {"region": "North", "category": "Furniture"}),
        ("Scenario 3 (quiet, seeded from detector: West+Household Items)", "sales", "2023-03-01", "2023-03-14",
         {"region": "West", "category": "Household Items"}),
    ]

    for label, metric, w0, w1, seed in scenarios:
        print(f"\n{'='*60}\n{label}: {metric} anomaly, {w0} to {w1}\n{'='*60}")
        impact = business_impact(df, metric, w0, w1, scope_filter=seed)
        print(f"Business impact: {impact}")

        chain = build_evidence_chain(df, metric, w0, w1, seed_scope=seed)
        for step in chain:
            print(" ->", step)

        final_scope = {s["dimension"]: s["value"] for s in chain if "value" in s}
        if final_scope:
            print("Volume/price check:", volume_or_price_driven(df, w0, w1, final_scope))