import sys
import os
import math
from typing import Optional
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "root_cause"))
from evidence_chain import business_impact, build_evidence_chain, volume_or_price_driven

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "alerts"))
from severity import classify_severity


def _period_average_z(series: pd.Series, window_start, window_end) -> Optional[dict]:
    window = series.loc[window_start:window_end]
    baseline = series.drop(window.index, errors="ignore")
    n = len(window)
    if n == 0 or len(baseline) < 5:
        return None
    se = baseline.std() / np.sqrt(n)
    if not se or se == 0 or np.isnan(se):
        return None
    z = (window.mean() - baseline.mean()) / se
    if np.isnan(z):
        return None
    return {"z_score": float(z), "window_mean": float(window.mean()), "baseline_mean": float(baseline.mean())}


def _build_windows(scan_start_ts, scan_end_ts, window_days, step_days):
    windows = []
    cursor = scan_start_ts
    while cursor <= scan_end_ts:
        w_end = min(cursor + pd.Timedelta(days=window_days - 1), scan_end_ts)
        windows.append((cursor, w_end))
        cursor = cursor + pd.Timedelta(days=step_days)
        if w_end >= scan_end_ts:
            break
    return windows


def _effective_n_tests(scan_start_ts, scan_end_ts, window_days, n_scopes: int) -> int:
  
    range_days = (scan_end_ts - scan_start_ts).days + 1
    independent_windows = max(1, math.ceil(range_days / window_days))
    return independent_windows * n_scopes


def _z_threshold_for(n_tests: int, false_positive_rate: float) -> float:
    from scipy.stats import norm
    alpha_per_test = false_positive_rate / max(n_tests, 1)
    threshold = float(norm.ppf(1 - alpha_per_test / 2))
    return min(threshold, 6.0)


def scan_for_anomalies(
    df: pd.DataFrame,
    scan_start: str,
    scan_end: str,
    metric: str = "sales",
    window_days: int = 14,
    step_days: Optional[int] = None,
    z_threshold: Optional[float] = None,
    false_positive_rate: float = 0.05,
    region_filter: Optional[str] = None,
) -> list:
   
    df = df.copy()
    df["order_date"] = pd.to_datetime(df["order_date"])
    scan_start_ts, scan_end_ts = pd.Timestamp(scan_start), pd.Timestamp(scan_end)
    regions = [region_filter] if region_filter else sorted(df["region"].dropna().unique())
    step_days = step_days or 1

    windows = _build_windows(scan_start_ts, scan_end_ts, window_days, step_days)
    if z_threshold is None:
        n_tests = _effective_n_tests(scan_start_ts, scan_end_ts, window_days, len(regions))
        z_threshold = _z_threshold_for(n_tests, false_positive_rate)

    hits = []
    for region in regions:
        sub = df[df["region"] == region]
        series = sub.groupby("order_date")[metric].sum().sort_index()

        for w_start, w_end in windows:
            if series.loc[w_start:w_end].empty:
                continue
            stat = _period_average_z(series, w_start, w_end)
            if stat is None or abs(stat["z_score"]) < z_threshold:
                continue

            w_start_str, w_end_str = w_start.strftime("%Y-%m-%d"), w_end.strftime("%Y-%m-%d")
            impact = business_impact(df, metric, w_start_str, w_end_str, scope_filter={"region": region})
            chain = build_evidence_chain(df, metric, w_start_str, w_end_str, seed_scope={"region": region})
            final_scope = {"region": region}
            for step in chain:
                if "value" in step and "dimension" in step:
                    final_scope[step["dimension"]] = step["value"]
            vp_check = volume_or_price_driven(df, w_start_str, w_end_str, scope_filter=final_scope)
            severity = classify_severity(impact)

            hits.append({
                "region": region, "window_start": w_start_str, "window_end": w_end_str,
                "metric": metric, "z_score": round(stat["z_score"], 2),
                "z_threshold_used": round(z_threshold, 2),
                "business_impact": impact, "evidence_chain": chain,
                "volume_price_margin_check": vp_check,
                "severity": severity.severity.value, "severity_reasoning": severity.reasoning,
            })

    hits.sort(key=lambda h: abs(h["z_score"]), reverse=True)
    deduped = []
    for h in hits:
        h_start, h_end = pd.Timestamp(h["window_start"]), pd.Timestamp(h["window_end"])
        overlaps_kept = any(
            h["region"] == k["region"]
            and not (h_end < pd.Timestamp(k["window_start"]) or h_start > pd.Timestamp(k["window_end"]))
            for k in deduped
        )
        if not overlaps_kept:
            deduped.append(h)
    return deduped


def scan_targeted(
    df: pd.DataFrame,
    scan_start: str,
    scan_end: str,
    region: str,
    category: str,
    metric: str = "sales",
    window_days: int = 14,
    step_days: Optional[int] = None,
    z_threshold: Optional[float] = None,
    false_positive_rate: float = 0.05,
) -> list:

    df = df.copy()
    df["order_date"] = pd.to_datetime(df["order_date"])
    scan_start_ts, scan_end_ts = pd.Timestamp(scan_start), pd.Timestamp(scan_end)
    step_days = step_days or 1

    windows = _build_windows(scan_start_ts, scan_end_ts, window_days, step_days)
    if z_threshold is None:
        n_tests = _effective_n_tests(scan_start_ts, scan_end_ts, window_days, n_scopes=1)
        z_threshold = _z_threshold_for(n_tests, false_positive_rate)

    sub = df[(df["region"] == region) & (df["category"] == category)]
    series = sub.groupby("order_date")[metric].sum().sort_index()

    hits = []
    for w_start, w_end in windows:
        if series.loc[w_start:w_end].empty:
            continue
        stat = _period_average_z(series, w_start, w_end)
        if stat is None or abs(stat["z_score"]) < z_threshold:
            continue

        w_start_str, w_end_str = w_start.strftime("%Y-%m-%d"), w_end.strftime("%Y-%m-%d")
        scope = {"region": region, "category": category}
        impact = business_impact(df, metric, w_start_str, w_end_str, scope_filter=scope)
        chain = build_evidence_chain(df, metric, w_start_str, w_end_str, seed_scope=scope)
        vp_check = volume_or_price_driven(df, w_start_str, w_end_str, scope_filter=scope)
        severity = classify_severity(impact)

        hits.append({
            "region": region, "window_start": w_start_str, "window_end": w_end_str,
            "metric": metric, "z_score": round(stat["z_score"], 2),
            "z_threshold_used": round(z_threshold, 2),
            "business_impact": impact, "evidence_chain": chain,
            "volume_price_margin_check": vp_check,
            "severity": severity.severity.value, "severity_reasoning": severity.reasoning,
        })

    hits.sort(key=lambda h: abs(h["z_score"]), reverse=True)
    deduped = []
    for h in hits:
        h_start, h_end = pd.Timestamp(h["window_start"]), pd.Timestamp(h["window_end"])
        overlaps_kept = any(
            not (h_end < pd.Timestamp(k["window_start"]) or h_start > pd.Timestamp(k["window_end"]))
            for k in deduped
        )
        if not overlaps_kept:
            deduped.append(h)
    return deduped


def check_exact_window(
    df: pd.DataFrame,
    window_start: str,
    window_end: str,
    region: str,
    category: str,
    metric: str = "sales",
) -> dict:

    df = df.copy()
    df["order_date"] = pd.to_datetime(df["order_date"])
    scope = {"region": region, "category": category}
    sub = df[(df["region"] == region) & (df["category"] == category)]
    series = sub.groupby("order_date")[metric].sum().sort_index()

    stat = _period_average_z(series, pd.Timestamp(window_start), pd.Timestamp(window_end))
    impact = business_impact(df, metric, window_start, window_end, scope_filter=scope)
    chain = build_evidence_chain(df, metric, window_start, window_end, seed_scope=scope)
    vp_check = volume_or_price_driven(df, window_start, window_end, scope_filter=scope)
    severity = classify_severity(impact)

    z = stat["z_score"] if stat else None
    return {
        "region": region, "category": category, "window_start": window_start, "window_end": window_end,
        "metric": metric, "z_score": round(z, 2) if z is not None else None,
        "is_significant": bool(z is not None and abs(z) >= 1.96),
        "business_impact": impact, "evidence_chain": chain,
        "volume_price_margin_check": vp_check,
        "severity": severity.severity.value, "severity_reasoning": severity.reasoning,
    }


if __name__ == "__main__":
    df = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])

    def _describe(h):
        main = next((s for s in h["evidence_chain"] if "value" in s and s.get("source") != "seeded_from_detector"), {})
        extra = f" (drilled: {main.get('dimension','?')}={main.get('value','?')})" if main else ""
        return (f"  {h['window_start']} to {h['window_end']} | {h['region']}{extra} | "
                f"z={h['z_score']} (threshold={h['z_threshold_used']}) | severity={h['severity']} | "
                f"impact={h['business_impact']['pct_change']}%")

    print("=== BROAD SCAN: full 2019-2023 range (expect exactly Scenario 1, nothing else) ===")
    all_hits = scan_for_anomalies(df, "2019-01-01", "2023-12-31", metric="sales")
    print(f"Hits: {len(all_hits)}")
    for h in all_hits:
        print(_describe(h))

    print()
    print("=== TARGETED SCAN: North+Furniture, profit (expect to find Scenario 2) ===")
    hits2 = scan_targeted(df, "2021-08-15", "2021-10-01", region="North", category="Furniture", metric="profit")
    for h in hits2:
        print(_describe(h))

    print()
    print("=== TARGETED SCAN: West+Household Items, sales (expect to find Scenario 3) ===")
    hits3 = scan_targeted(df, "2023-02-15", "2023-04-01", region="West", category="Household Items", metric="sales")
    for h in hits3:
        print(_describe(h))

    print()
    print("=== CONTROL: unrelated combo, should stay clean ===")
    control = scan_targeted(df, "2021-08-15", "2021-10-01", region="South", category="Furniture", metric="profit")
    print(f"Hits: {len(control)}" + (" -- correctly clean" if len(control) == 0 else " -- UNEXPECTED"))