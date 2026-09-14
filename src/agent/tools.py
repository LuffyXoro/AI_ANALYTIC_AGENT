import sys
import os
import json
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "root_cause"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analytics"))

from evidence_chain import build_evidence_chain, business_impact, volume_or_price_driven
from kpi_engine import compute_kpis, filter_transactions
from trend_engine import detect_trend

KNOWN_ANOMALIES = [
    {
        "id": "scenario_1", "metric": "sales", "window_start": "2022-06-01", "window_end": "2022-06-14",
        "region": "South", "category": "Electric Appliances",
        "detection_mode": "blind",  # loud, company-wide-visible -- blind top-down search correctly
                                     # reconstructs it (see docs/04); business impact should be
                                     # measured company-wide, not pre-seeded to the sub-scope
        "summary": "Company-wide revenue fell 12.9%, driven by a 44.9% drop in South region, "
                    "with Electric Appliances the largest single contributor (-79.5%). Volume-driven.",
    },
    {
        "id": "scenario_2", "metric": "profit", "window_start": "2021-09-01", "window_end": "2021-09-14",
        "region": "North", "category": "Furniture",
        "detection_mode": "seeded",  # quiet at company level -- blind search chases noise and
                                       # returns the WRONG answer entirely (see docs/04, Finding 3);
                                       # must be seeded with the region/category the original
                                       # detector actually flagged
        "summary": "North+Furniture profit fell 57.65% while revenue stayed flat -- a pure "
                    "margin/discount-driven anomaly, not a volume problem.",
    },
    {
        "id": "scenario_3", "metric": "sales", "window_start": "2023-03-01", "window_end": "2023-03-14",
        "region": "West", "category": "Household Items",
        "detection_mode": "seeded",  # same reasoning as scenario_2 -- quiet, company-wide impact <1%
        "summary": "West+Household Items revenue fell 43.74%, but company-wide impact was under 1% -- "
                    "a quiet anomaly invisible at the top-line level.",
    },
]


def tool_get_kpis(start_date: str, end_date: str, region: str = None, category: str = None) -> dict:
    df = _load_df()
    sub = filter_transactions(df, start_date=start_date, end_date=end_date, region=region, category=category)
    if sub.empty:
        return {"error": "No transactions found for the given filters."}
    return compute_kpis(sub).as_dict()


def tool_get_trend(metric: str, target_date: str, period: str = "wow", region: str = None) -> dict:
    df = _load_df()
    result = detect_trend(df, target_date=target_date, metric=metric, period=period, region=region)
    return {
        "metric": result.metric, "period": result.period,
        "current_value": result.current_value, "comparison_value": result.comparison_value,
        "pct_change": result.pct_change, "direction": result.direction,
        "baseline_flagged": result.baseline_flagged,
    }


def tool_get_root_cause(metric: str, window_start: str, window_end: str,
                         region: str = None, category: str = None) -> dict:

    df = _load_df()
    seed = {}
    if region: seed["region"] = region
    if category: seed["category"] = category
    seed = seed or None

    impact = business_impact(df, metric, window_start, window_end, scope_filter=seed)
    chain = build_evidence_chain(df, metric, window_start, window_end, seed_scope=seed)

    if seed:
        vp_scope = seed
    else:
        first_step = next((s for s in chain if "value" in s), None)
        vp_scope = {first_step["dimension"]: first_step["value"]} if first_step else {}
    vp_check = volume_or_price_driven(df, window_start, window_end, scope_filter=vp_scope) if vp_scope else None

    
    vp_scope_mask = pd.Series(True, index=df.index)
    for col, val in vp_scope.items():
        vp_scope_mask &= df[col] == val
    vp_window_orders = df[vp_scope_mask & df["order_date"].between(window_start, window_end)]["order_id"].nunique()
    low_sample_warning = (
        f"CAUTION: only {vp_window_orders} orders in the scope used for volume_price_margin_check -- "
        f"treat that reading as indicative, not reliable."
        if vp_window_orders < 30 else None
    )

    return {
        "business_impact": impact,
        "evidence_chain": chain,
        "volume_price_margin_check": vp_check,
        "volume_price_margin_check_scope": vp_scope,
        "low_sample_warning": low_sample_warning,
    }


def tool_list_known_anomalies() -> dict:
    
    return {"known_anomalies": KNOWN_ANOMALIES,
            "note": "This project detects anomalies in known, tested windows -- it does not "
                     "continuously scan every date/region/category combination live."}


_df_cache = None
def _load_df():
    global _df_cache
    if _df_cache is None:
        _df_cache = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])
    return _df_cache


# --- Groq/OpenAI function-calling schemas ---
TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "tool_get_kpis",
        "description": "Get revenue, orders, profit, AOV, profit margin, and discount rate for a date range, optionally filtered by region and/or category.",
        "parameters": {"type": "object", "properties": {
            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            "region": {"type": ["string", "null"], "description": "East, North, South, or West. Use null for company-wide."},
            "category": {"type": ["string", "null"], "description": "e.g. Electric Appliances, Furniture. Use null for all categories."},
        }, "required": ["start_date", "end_date"]}}},
    {"type": "function", "function": {
        "name": "tool_get_trend",
        "description": "Check how a metric changed vs. a prior period (day/week/month/year ago) on a specific date.",
        "parameters": {"type": "object", "properties": {
            "metric": {"type": "string", "description": "e.g. sales, profit"},
            "target_date": {"type": "string", "description": "YYYY-MM-DD"},
            "period": {"type": "string", "enum": ["dod", "wow", "mom", "yoy"]},
            "region": {"type": ["string", "null"], "description": "Optional region filter, null if not needed"},
        }, "required": ["metric", "target_date"]}}},
    {"type": "function", "function": {
        "name": "tool_get_root_cause",
        "description": "Get business impact and the auto-drilled evidence chain (which region/category/sub_category explains a deviation) for a metric over a date window. Pass region/category if already known (e.g. from list_known_anomalies) to avoid unreliable blind search on quiet anomalies.",
        "parameters": {"type": "object", "properties": {
            "metric": {"type": "string"},
            "window_start": {"type": "string", "description": "YYYY-MM-DD"},
            "window_end": {"type": "string", "description": "YYYY-MM-DD"},
            "region": {"type": ["string", "null"]},
            "category": {"type": ["string", "null"]},
        }, "required": ["metric", "window_start", "window_end"]}}},
    {"type": "function", "function": {
        "name": "tool_list_known_anomalies",
        "description": "List the anomalies this system has already detected and verified. Use this first when the user asks a general question like 'what's wrong' or 'what are the anomalies' before drilling into specifics.",
        "parameters": {"type": "object", "properties": {}}}},
]

TOOL_FUNCTIONS = {
    "tool_get_kpis": tool_get_kpis,
    "tool_get_trend": tool_get_trend,
    "tool_get_root_cause": tool_get_root_cause,
    "tool_list_known_anomalies": tool_list_known_anomalies,
}


if __name__ == "__main__":
   
    print("=== tool_get_kpis (South, Scenario 1 window) ===")
    print(json.dumps(tool_get_kpis("2022-06-01", "2022-06-14", region="South"), indent=2))

    print("\n=== tool_get_trend (South sales, WoW, 2022-06-01) ===")
    print(json.dumps(tool_get_trend("sales", "2022-06-01", period="wow", region="South"), indent=2))

    print("\n=== tool_get_root_cause (Scenario 1, blind) ===")
    print(json.dumps(tool_get_root_cause("sales", "2022-06-01", "2022-06-14"), indent=2))

    print("\n=== tool_list_known_anomalies ===")
    print(json.dumps(tool_list_known_anomalies(), indent=2))