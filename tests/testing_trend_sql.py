import duckdb
con = duckdb.connect()
con.execute("CREATE TABLE transactions AS SELECT * FROM read_csv_auto('data/processed/transactions_with_anomalies.csv')")

query = """
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
WHERE order_date BETWEEN DATE '2022-06-01' AND DATE '2022-06-14' AND region = 'South'
ORDER BY order_date
"""
result = con.execute(query).fetchdf()
print(result.to_string(index=False))