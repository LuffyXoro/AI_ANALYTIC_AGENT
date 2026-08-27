'''
The imp. trends will be stored in this file. 
The trends will be calculated based on the KPIs and the data available in the transactions table. 
The trends will be used to identify patterns and anomalies in the data over time.
'''

-- Table expected: transactions
--   (order_id, order_date, sales, quantity, discount, profit, region, state,
--    city_type, outlet_type, category, sub_category, segment, ship_mode)

-- DAILY REVENUE SERIES (THE BASE)
WITH daily_revenue AS (
    SELECT
        order_date,
        SUM(sales) AS revenue,
        COUNT(DISTINCT order_id) AS orders,
        SUM(profit) AS profit
    FROM transactions
    GROUP BY order_date
),

-- LAG() to pull each comparison period's value onto the same row
trend AS (
    SELECT
        order_date,
        revenue,
        orders,
        profit,
        LAG(revenue, 1)   OVER (ORDER BY order_date) AS revenue_1d_ago,   -- DoD
        LAG(revenue, 7)   OVER (ORDER BY order_date) AS revenue_7d_ago,   -- WoW
        LAG(revenue, 30)  OVER (ORDER BY order_date) AS revenue_30d_ago,  -- MoM (approx)
        LAG(revenue, 365) OVER (ORDER BY order_date) AS revenue_365d_ago  -- YoY
    FROM daily_revenue
)

-- Percent change
SELECT
    order_date,
    revenue,
    revenue_1d_ago,
    ROUND(100.0 * (revenue - revenue_1d_ago) / NULLIF(revenue_1d_ago, 0), 2) AS dod_pct_change,
    ROUND(100.0 * (revenue - revenue_7d_ago) / NULLIF(revenue_7d_ago, 0), 2) AS wow_pct_change,
    ROUND(100.0 * (revenue - revenue_30d_ago) / NULLIF(revenue_30d_ago, 0), 2) AS mom_pct_change,
    ROUND(100.0 * (revenue - revenue_365d_ago) / NULLIF(revenue_365d_ago, 0), 2) AS yoy_pct_change,
    CASE
        WHEN revenue_7d_ago IS NULL THEN 'insufficient_history'
        WHEN (revenue - revenue_7d_ago) / NULLIF(revenue_7d_ago, 0) > 0.05 THEN 'increasing'
        WHEN (revenue - revenue_7d_ago) / NULLIF(revenue_7d_ago, 0) < -0.05 THEN 'decreasing'
        ELSE 'stable'
    END AS wow_direction
FROM trend
ORDER BY order_date;

-- Grouped by REGION

WITH daily_region_revenue AS (
    SELECT order_date, region, SUM(sales) AS revenue
    FROM transactions
    GROUP BY order_date, region
),
trend_by_region AS (
    SELECT
        order_date,
        region,
        revenue,
        LAG(revenue, 7) OVER (PARTITION BY region ORDER BY order_date) AS revenue_7d_ago
    FROM daily_region_revenue
)
SELECT
    order_date,
    region,
    revenue,
    ROUND(100.0 * (revenue - revenue_7d_ago) / NULLIF(revenue_7d_ago, 0), 2) AS wow_pct_change
FROM trend_by_region
WHERE order_date BETWEEN DATE '2022-06-01' AND DATE '2022-06-14'
ORDER BY region, order_date;