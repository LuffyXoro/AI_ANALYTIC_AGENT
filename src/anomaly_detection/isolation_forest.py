"""
evaluating against known ground truth.

Ground truth: every feature row (date, region, category) that falls inside
one of the 3 documented injection windows is
labeled a true anomaly. 

Isolation Forest : it isolates points by repeatedly splitting on
random features/thresholds. Anomalies are, on average, isolated in fewer
splits than normal points (they sit apart from the bulk of the data), so a
row's "path length" becomes an anomaly score.

"""

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest

FEATURES_PATH = "data/processed/daily_region_category_features.csv"
SCORED_OUT_PATH = "data/processed/isolation_forest_scored.csv"

FEATURE_COLUMNS = ["revenue", "orders", "avg_order_value", "profit", "profit_margin", "avg_discount_rate"]

SCENARIOS = [
    dict(name="s1_south_electric_appliances_severe", region="South", category="Electric Appliances",
         start="2022-06-01", end="2022-06-14"),
    # Scenario 1 also touched South's OTHER 5 categories moderately -- ground truth
    # includes them too, tagged separately so we can see if IF catches the severe
    # cut better than the moderate one.
    dict(name="s1_south_other_categories_moderate", region="South", category=None,
         start="2022-06-01", end="2022-06-14", exclude_category="Electric Appliances"),
    dict(name="s2_north_furniture_margin_squeeze", region="North", category="Furniture",
         start="2021-09-01", end="2021-09-14"),
    dict(name="s3_west_household_multimetric", region="West", category="Household Items",
         start="2023-03-01", end="2023-03-14"),
]


def label_ground_truth(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["true_anomaly"] = False
    df["scenario"] = None

    for s in SCENARIOS:
        mask = (
            (df["region"] == s["region"])
            & (df["order_date"].between(s["start"], s["end"]))
        )
        if s["category"] is not None:
            mask &= df["category"] == s["category"]
        if s.get("exclude_category"):
            mask &= df["category"] != s["exclude_category"]

        df.loc[mask, "true_anomaly"] = True
        df.loc[mask, "scenario"] = s["name"]

    return df


def train_and_score(df: pd.DataFrame, contamination: float, seed: int = 42) -> pd.DataFrame:
    model = IsolationForest(contamination=contamination, random_state=seed, n_estimators=200)
    X = df[FEATURE_COLUMNS].values
    df = df.copy()
    df["if_prediction"] = model.fit_predict(X)  # -1 = anomaly, 1 = normal
    df["if_anomaly_score"] = -model.decision_function(X)  # higher = more anomalous
    df["predicted_anomaly"] = df["if_prediction"] == -1
    return df


def evaluate(df: pd.DataFrame) -> dict:
    tp = ((df["true_anomaly"]) & (df["predicted_anomaly"])).sum()
    fn = ((df["true_anomaly"]) & (~df["predicted_anomaly"])).sum()
    fp = ((~df["true_anomaly"]) & (df["predicted_anomaly"])).sum()
    tn = ((~df["true_anomaly"]) & (~df["predicted_anomaly"])).sum()

    recall = tp / (tp + fn) if (tp + fn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0

    return {
        "true_positives": int(tp), "false_negatives": int(fn),
        "false_positives": int(fp), "true_negatives": int(tn),
        "recall": round(recall, 3), "precision": round(precision, 3),
        "total_true_anomalies": int(df["true_anomaly"].sum()),
        "total_flagged": int(df["predicted_anomaly"].sum()),
    }


if __name__ == "__main__":
    df = pd.read_csv(FEATURES_PATH, parse_dates=["order_date"])
    df = label_ground_truth(df)

    print(f"Ground truth: {df['true_anomaly'].sum()} anomalous rows out of {len(df):,} total "
          f"({100*df['true_anomaly'].mean():.2f}%)")

    print("\n=== Tuning contamination rate ===")
    for contamination in [0.01, 0.02, 0.05, 0.10]:
        scored = train_and_score(df, contamination=contamination)
        result = evaluate(scored)
        print(f"contamination={contamination:<5} -> {result}")

    print("\n=== Per-scenario recall at contamination=0.02 ===")
    scored = train_and_score(df, contamination=0.02)
    for s in SCENARIOS:
        sub = scored[scored["scenario"] == s["name"]]
        if len(sub) == 0:
            print(f"  {s['name']}: no ground-truth rows found (check window/dimension)")
            continue
        recall = sub["predicted_anomaly"].mean()
        print(f"  {s['name']}: {sub['predicted_anomaly'].sum()}/{len(sub)} flagged (recall={recall:.2f})")

    scored.to_csv(SCORED_OUT_PATH, index=False)
    print(f"\nScored data saved -> {SCORED_OUT_PATH}")