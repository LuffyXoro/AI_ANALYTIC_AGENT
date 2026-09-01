-- Table expected: transactions
--   (order_id, order_date, sales, quantity, discount, profit, region, state,
--    city_type, outlet_type, category, sub_category, segment, ship_mode)

-- 1. Revenue

SELECT SUM(sales) AS revenue
FROM transactions;

-- 2. Orders

SELECT COUNT(DISTINCT order_id) AS orders
FROM transactions;

-- 3. Units Sold
SELECT SUM(quantity) AS units_sold
FROM transactions;

-- 4. Average Order Value (AOV)
SELECT SUM(sales) / COUNT(DISTINCT order_id) AS avg_order_value
FROM transactions;

-- 5. Profit
SELECT SUM(profit) AS profit
FROM transactions;

-- 6. Profit Margin
SELECT SUM(profit) / NULLIF(SUM(sales), 0) AS profit_margin
FROM transactions;

-- 7. Discount Rate

SELECT AVG(discount) AS avg_discount_rate
FROM transactions;

SELECT SUM(sales * discount) / NULLIF(SUM(sales), 0) AS revenue_weighted_discount_rate
FROM transactions;

-- All KPIs

SELECT
    SUM(sales)                                   AS revenue,
    COUNT(DISTINCT order_id)                     AS orders,
    SUM(quantity)                                AS units_sold,
    SUM(sales) / COUNT(DISTINCT order_id)        AS avg_order_value,
    SUM(profit)                                  AS profit,
    SUM(profit) / NULLIF(SUM(sales), 0)          AS profit_margin,
    AVG(discount)                                AS avg_discount_rate
FROM transactions;

-- KPIs filterable by date range and dimension

SELECT
    SUM(sales)                                   AS revenue,
    COUNT(DISTINCT order_id)                     AS orders,
    SUM(quantity)                                AS units_sold,
    SUM(sales) / NULLIF(COUNT(DISTINCT order_id), 0) AS avg_order_value,
    SUM(profit)                                  AS profit,
    SUM(profit) / NULLIF(SUM(sales), 0)          AS profit_margin,
    AVG(discount)                                AS avg_discount_rate
FROM transactions
WHERE order_date BETWEEN {start_date} AND {end_date}
  AND (region = {region} OR {region} IS NULL)
  AND (category = {category} OR {category} IS NULL);

-- KPIs broken down by a dimension

SELECT
    region,
    SUM(sales)                                   AS revenue,
    COUNT(DISTINCT order_id)                     AS orders,
    SUM(profit)                                  AS profit,
    SUM(profit) / NULLIF(SUM(sales), 0)          AS profit_margin
FROM transactions
GROUP BY region
ORDER BY revenue DESC;


