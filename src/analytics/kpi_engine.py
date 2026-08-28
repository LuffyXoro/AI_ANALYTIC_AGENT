""" AI AGENT
Excluded on purpose: Return Rate, Revenue per Customer. The dataset has no
returns data and no repeat customers — see docs/00_dataset_and_eda.md.
"""


# cross-verified against sql kpi engine,plus a passing test suite

from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class KPISnapshot:
    revenue: float
    orders: int
    units_sold: int
    avg_order_value: float
    profit: float
    profit_margin: float
    avg_discount_rate: float

    def as_dict(self) -> dict:
        return {
            "revenue": round(self.revenue, 2),
            "orders": self.orders,
            "units_sold": self.units_sold,
            "avg_order_value": round(self.avg_order_value, 2),
            "profit": round(self.profit, 2),
            "profit_margin": round(self.profit_margin, 4),
            "avg_discount_rate": round(self.avg_discount_rate, 4),
        }


def filter_transactions(
    df: pd.DataFrame,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    region: Optional[str] = None,
    category: Optional[str] = None,
) -> pd.DataFrame:
    """
    every tool in the agent (KPI Tool, Trend
    Tool, Root Cause Tool) needs the same date/region/category filtering
    logic. Keeping it in one place means a bug fix or a new filter dimension
    only needs to happen once.
    """
    out = df
    if start_date is not None:
        out = out[out["order_date"] >= pd.to_datetime(start_date).date()]
    if end_date is not None:
        out = out[out["order_date"] <= pd.to_datetime(end_date).date()]
    if region is not None:
        out = out[out["region"] == region]
    if category is not None:
        out = out[out["category"] == category]
    return out


def compute_kpis(df: pd.DataFrame) -> KPISnapshot:

    if df.empty:
        raise ValueError("compute_kpis received an empty slice — check your filters")

    revenue = df["sales"].sum()
    orders = df["order_id"].nunique()
    units_sold = int(df["quantity"].sum())
    profit = df["profit"].sum()

    return KPISnapshot(
        revenue=revenue,
        orders=orders,
        units_sold=units_sold,
        avg_order_value=revenue / orders,
        profit=profit,
        profit_margin=(profit / revenue) if revenue else 0.0,
        avg_discount_rate=df["discount"].mean(),
    )


def kpis_by_dimension(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if dimension not in df.columns:
        raise ValueError(f"'{dimension}' is not a column in the transactions data")

    grouped = df.groupby(dimension).apply(
        lambda g: pd.Series(compute_kpis(g).as_dict())
    )
    return grouped.sort_values("revenue", ascending=False)


if __name__ == "__main__":
    df = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])
    df["order_date"] = df["order_date"].dt.date

    overall = compute_kpis(df)
    print("Overall KPIs:")
    for k, v in overall.as_dict().items():
        print(f"  {k}: {v}")

    print("\nBy region:")
    print(kpis_by_dimension(df, "region"))