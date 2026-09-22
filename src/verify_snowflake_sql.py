import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from snowflake_client import get_connection

KPI_SUMMARY_QUERY = """
    SELECT
        SUM(sales)                                   AS revenue,
        COUNT(DISTINCT order_id)                     AS orders,
        SUM(quantity)                                AS units_sold,
        SUM(sales) / COUNT(DISTINCT order_id)        AS avg_order_value,
        SUM(profit)                                  AS profit,
        SUM(profit) / NULLIF(SUM(sales), 0)          AS profit_margin,
        AVG(discount)                                AS avg_discount_rate
    FROM transactions
"""

REGION_BREAKDOWN_QUERY = """
    SELECT region, SUM(sales) AS revenue, COUNT(DISTINCT order_id) AS orders,
           SUM(profit) AS profit, SUM(profit)/NULLIF(SUM(sales),0) AS profit_margin
    FROM transactions GROUP BY region ORDER BY revenue DESC
"""
 
TREND_WOW_QUERY = """
    WITH daily_region_revenue AS (
        SELECT order_date, region, SUM(sales) AS revenue
        FROM transactions
        GROUP BY order_date, region
    ),
    trend_by_region AS (
        SELECT
            order_date, region, revenue,
            LAG(revenue, 7) OVER (PARTITION BY region ORDER BY order_date) AS revenue_7d_ago
        FROM daily_region_revenue
    )
    SELECT
        order_date, region, revenue,
        ROUND(100.0 * (revenue - revenue_7d_ago) / NULLIF(revenue_7d_ago, 0), 2) AS wow_pct_change
    FROM trend_by_region
    WHERE order_date BETWEEN '2022-06-01' AND '2022-06-14' AND region = 'South'
    ORDER BY order_date
"""


def run_and_print(cur, label, query):
    print(f"\n=== {label} ===")
    cur.execute(query)
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    print(cols)
    for r in rows[:15]:
        print(r)
    return cols, rows

EXPECTED = {
    "revenue": 2505921167.3,
    "orders": 99916,
    "units_sold": 548897,
    "avg_order_value": 25080.28,
    "profit": 375078596.38,
    "profit_margin": 0.1497,
    "avg_discount_rate": 0.2515,
}
 
 
if __name__ == "__main__":
    with get_connection() as conn:
        cur = conn.cursor()
 
        cols, rows = run_and_print(cur, "KPI Summary", KPI_SUMMARY_QUERY)
        result = dict(zip([c.lower() for c in cols], rows[0]))
 
        print(" Cross-check against DuckDB values ")
        all_match = True
        for key, expected_val in EXPECTED.items():
            actual_val = float(result[key])
            match = abs(actual_val - expected_val) < max(1, abs(expected_val) * 0.001)
            all_match &= match
            status = "OK" if match else "MISMATCH"
            print(f"  {key}: snowflake={actual_val}  duckdb={expected_val}  [{status}]")
        print(f"\nOverall: {'ALL MATCH' if all_match else 'MISMATCH FOUND -- investigate before trusting Snowflake queries'}")
 
        run_and_print(cur, "Region Breakdown", REGION_BREAKDOWN_QUERY)
        run_and_print(cur, "Trend Engine: South WoW during Scenario 1 window", TREND_WOW_QUERY)