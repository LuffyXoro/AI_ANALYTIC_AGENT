"""
1. ROW REMOVAL (volume-driven anomalies):"orders dropped, AOV didn't move, so this isn't a pricing issue."

2. DISCOUNT-MARGIN SQUEEZE (price-driven anomalies): discount is raised and profit is recomputed using each row's
   OWN original margin (profit / (sales * (1-discount))) ,Revenue stays
   exactly flat, which is the point: it isolates a pure margin story.

Scenarios (all seeded, non-overlapping in date/dimension, independently
verifiable):

  1. "South region softness, driven by Electric Appliances" (row removal)
     2022-06-01 to 2022-06-14. South+Electric Appliances -75% orders,
     South+other categories -35% orders.

  2. "North Furniture profit-margin squeeze" (discount-margin squeeze)
     2021-09-01 to 2021-09-14. North+Furniture: discount +0.35 (capped 0.75).
     Revenue unchanged; profit falls purely from the discount effect.

  3. "West Household Items multi-metric anomaly" (squeeze + row removal)
     2023-03-01 to 2023-03-14. West+Household Items: discount +0.20 (capped
     0.70) on all matching rows, then -20% of those (already-squeezed) orders
     removed. Deliberately small at the company-revenue level -- the point of
     this scenario is that the top line looks nearly normal while orders,
     discount, and profit all move underneath it.
"""

import pandas as pd
import numpy as np

IN_PATH = "data/processed/clean_data.csv"
OUT_PATH = "data/processed/transactions_with_anomalies.csv"
MANIFEST_PATH = "data/processed/anomaly_injection_manifest.csv"

SEED = 42
MAX_DISCOUNT = 0.90  

def _row_removal(df, rng, scenario_id, window_start, window_end, region,
                  severe_category, severe_rate, other_rate):
    """Volume-driven anomaly: randomly drop a fraction of orders in-window."""
    in_window = df["order_date"].between(window_start, window_end)
    in_region = df["region"] == region
    in_severe_cat = df["category"] == severe_category

    severe_mask = in_window & in_region & in_severe_cat
    other_mask = in_window & in_region & ~in_severe_cat

    def pick(mask, rate):
        idx = df.index[mask]
        n = int(round(len(idx) * rate))
        return pd.Index(rng.choice(idx, size=n, replace=False)) if n else pd.Index([])

    drop_severe = pick(severe_mask, severe_rate)
    drop_other = pick(other_mask, other_rate) if other_rate > 0 else pd.Index([])
    drop_idx = drop_severe.union(drop_other)

    manifest_rows = df.loc[drop_idx].copy()
    manifest_rows["scenario_id"] = scenario_id
    manifest_rows["change_type"] = np.where(
        manifest_rows.index.isin(drop_severe), "row_removed_severe", "row_removed_moderate"
    )
    return drop_idx, manifest_rows

def _discount_squeeze(df, scenario_id, window_start, window_end, region, category, discount_boost):
    """Price-driven anomaly: raise discount, recompute profit from each row's own margin."""
    mask = (
        df["order_date"].between(window_start, window_end)
        & (df["region"] == region)
        & (df["category"] == category)
    )
    idx = df.index[mask]

    original_margin = df.loc[idx, "profit"] / (df.loc[idx, "sales"] * (1 - df.loc[idx, "discount"]))
    new_discount = (df.loc[idx, "discount"] + discount_boost).clip(upper=MAX_DISCOUNT)
    new_profit = df.loc[idx, "sales"] * (1 - new_discount) * original_margin

    manifest_rows = df.loc[idx].copy()
    manifest_rows["scenario_id"] = scenario_id
    manifest_rows["change_type"] = "discount_margin_squeeze"
    manifest_rows["original_discount"] = df.loc[idx, "discount"]
    manifest_rows["original_profit"] = df.loc[idx, "profit"]

    df.loc[idx, "discount"] = new_discount
    df.loc[idx, "profit"] = new_profit

    manifest_rows["new_discount"] = new_discount
    manifest_rows["new_profit"] = new_profit
    return idx, manifest_rows

def inject(in_path: str = IN_PATH, out_path: str = OUT_PATH, manifest_path: str = MANIFEST_PATH):
    rng = np.random.default_rng(SEED)
    df = pd.read_csv(in_path, parse_dates=["order_date"])

    manifests = []

    # Scenario 1: South region softness, driven by Electric Appliances (row removal)
    drop_idx_1, manifest_1 = _row_removal(
        df, rng, scenario_id="s1_south_electric_appliances",
        window_start="2022-06-01", window_end="2022-06-14",
        region="South", severe_category="Electric Appliances",
        severe_rate=0.75, other_rate=0.35,
    )
    manifests.append(manifest_1)

    # Scenario 2: North Furniture profit-margin squeeze (discount-margin squeeze)
    sq_idx_2, manifest_2 = _discount_squeeze(
        df, scenario_id="s2_north_furniture_margin_squeeze",
        window_start="2021-09-01", window_end="2021-09-14",
        region="North", category="Furniture", discount_boost=0.35,
    )
    manifests.append(manifest_2)

    # Scenario 3: West Household Items multi-metric anomaly (squeeze, then removal)
    sq_idx_3, manifest_3a = _discount_squeeze(
        df, scenario_id="s3_west_household_multimetric",
        window_start="2023-03-01", window_end="2023-03-14",
        region="West", category="Household Items", discount_boost=0.20,
    )
    drop_idx_3, manifest_3b = _row_removal(
        df, rng, scenario_id="s3_west_household_multimetric",
        window_start="2023-03-01", window_end="2023-03-14",
        region="West", severe_category="Household Items",
        severe_rate=0.20, other_rate=0.0,
    )
    manifests.append(manifest_3a)
    manifests.append(manifest_3b)

    all_drop_idx = drop_idx_1.union(drop_idx_3)

    manifest = pd.concat(manifests, ignore_index=False)
    manifest.to_csv(manifest_path, index=True, index_label="original_row_index")

    result = df.drop(index=all_drop_idx).reset_index(drop=True)
    result.to_csv(out_path, index=False)

    print(f"Scenario 1 (row removal):      {len(drop_idx_1):,} rows removed")
    print(f"Scenario 2 (margin squeeze):   {len(sq_idx_2):,} rows discount/profit adjusted")
    print(f"Scenario 3 (squeeze+removal):  {len(sq_idx_3):,} rows adjusted, {len(drop_idx_3):,} rows removed")
    print(f"Remaining rows: {len(result):,} -> {out_path}")
    print(f"Manifest ({len(manifest):,} entries) -> {manifest_path}")
    return result, manifest

if __name__ == "__main__":
    inject()