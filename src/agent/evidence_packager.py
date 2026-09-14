import sys
import os
from dataclasses import dataclass, asdict
from typing import Optional
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "root_cause"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analytics"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "anomaly_detection"))

from evidence_chain import build_evidence_chain, business_impact, volume_or_price_driven
from contribution import contribution_analysis
from kpi_engine import compute_kpis, filter_transactions


@dataclass
class AnomalyEvidence:
    metric: str
    window_start: str
    window_end: str
    seed_scope: Optional[dict]

    business_impact: dict           # from evidence_chain.business_impact()
    evidence_chain: list             # from evidence_chain.build_evidence_chain()
    volume_price_margin_check: str   # from evidence_chain.volume_or_price_driven()
    kpi_snapshot_during_window: dict  # from kpi_engine.compute_kpis()
    kpi_snapshot_baseline: dict       # period before the window
    low_sample_warning: Optional[str] = None  

    def to_dict(self) -> dict:
        return asdict(self)


def package_evidence(
    df: pd.DataFrame,
    metric: str,
    window_start: str,
    window_end: str,
    seed_scope: Optional[dict] = None,
) -> AnomalyEvidence:
    
    impact = business_impact(df, metric, window_start, window_end, scope_filter=seed_scope)
    chain = build_evidence_chain(df, metric, window_start, window_end, seed_scope=seed_scope)

    final_scope = seed_scope.copy() if seed_scope else {}
    for step in chain:
        if "value" in step and "dimension" in step:
            final_scope[step["dimension"]] = step["value"]

    vp_check = volume_or_price_driven(df, window_start, window_end, scope_filter=final_scope or {})

    scope_mask = pd.Series(True, index=df.index)
    for col, val in final_scope.items():
        scope_mask &= df[col] == val
    scoped_df = df[scope_mask]

    window_df = filter_transactions(scoped_df, start_date=window_start, end_date=window_end)
    baseline_df = scoped_df[~scoped_df["order_date"].between(window_start, window_end)]

    window_kpis = compute_kpis(window_df).as_dict() if len(window_df) else {}
    baseline_kpis = compute_kpis(baseline_df).as_dict() if len(baseline_df) else {}

   
    window_order_count = window_kpis.get("orders", 0)
    low_sample_warning = (
        f"CAUTION: only {window_order_count} orders in this window at the final scope -- "
        f"volume_price_margin_check may reflect small-sample noise rather than a real signal."
        if window_order_count < 30 else None
    )

    return AnomalyEvidence(
        metric=metric,
        window_start=window_start,
        window_end=window_end,
        seed_scope=seed_scope,
        business_impact=impact,
        evidence_chain=chain,
        volume_price_margin_check=vp_check,
        kpi_snapshot_during_window=window_kpis,
        kpi_snapshot_baseline=baseline_kpis,
        low_sample_warning=low_sample_warning,
    )


if __name__ == "__main__":
    import json

    df = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])

    print("=== Scenario 1 evidence package (blind search) ===")
    evidence1 = package_evidence(df, metric="sales", window_start="2022-06-01", window_end="2022-06-14")
    print(json.dumps(evidence1.to_dict(), indent=2, default=str))

    print("\n=== Scenario 2 evidence package (seeded) ===")
    evidence2 = package_evidence(
        df, metric="profit", window_start="2021-09-01", window_end="2021-09-14",
        seed_scope={"region": "North", "category": "Furniture"},
    )
    print(json.dumps(evidence2.to_dict(), indent=2, default=str))