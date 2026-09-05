import duckdb
con = duckdb.connect()
con.execute("CREATE TABLE transactions AS SELECT * FROM read_csv_auto('data/processed/transactions_with_anomalies.csv')")

print("=== All-KPIs summary query ===")
result = con.execute("""
    SELECT
        SUM(sales)                                   AS revenue,
        COUNT(DISTINCT order_id)                     AS orders,
        SUM(quantity)                                AS units_sold,
        SUM(sales) / COUNT(DISTINCT order_id)        AS avg_order_value,
        SUM(profit)                                  AS profit,
        SUM(profit) / NULLIF(SUM(sales), 0)          AS profit_margin,
        AVG(discount)                                AS avg_discount_rate
    FROM transactions
""").fetchdf()
print(result.T)

print("\n=== By-region breakdown ===")
result2 = con.execute("""
    SELECT region, SUM(sales) AS revenue, COUNT(DISTINCT order_id) AS orders,
           SUM(profit) AS profit, SUM(profit)/NULLIF(SUM(sales),0) AS profit_margin
    FROM transactions GROUP BY region ORDER BY revenue DESC
""").fetchdf()
print(result2)