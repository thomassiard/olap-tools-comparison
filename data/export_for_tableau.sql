-- Dimension tables (small, full export)
SELECT * FROM instacart.aisles INTO OUTFILE '/data/tableau_aisles.csv' FORMAT CSVWithNames;
SELECT * FROM instacart.departments INTO OUTFILE '/data/tableau_departments.csv' FORMAT CSVWithNames;
SELECT * FROM instacart.products INTO OUTFILE '/data/tableau_products.csv' FORMAT CSVWithNames;

-- Orders table (3.4M rows, manageable for Tableau Public)
SELECT * FROM instacart.orders INTO OUTFILE '/data/tableau_orders.csv' FORMAT CSVWithNames;

-- Pre-aggregated summary: department-level order stats (small, great for dashboards)
SELECT
    d.department,
    a.aisle,
    count() AS times_ordered,
    sum(op.reordered) AS times_reordered,
    round(sum(op.reordered) / count() * 100, 2) AS reorder_rate_pct
FROM instacart.order_products_prior op
JOIN instacart.products p ON op.product_id = p.product_id
JOIN instacart.aisles a ON p.aisle_id = a.aisle_id
JOIN instacart.departments d ON p.department_id = d.department_id
GROUP BY d.department, a.aisle
ORDER BY times_ordered DESC
INTO OUTFILE '/data/tableau_department_aisle_summary.csv' FORMAT CSVWithNames;

-- Pre-aggregated summary: order patterns by day-of-week and hour
SELECT
    order_dow,
    order_hour_of_day,
    count() AS order_count,
    round(avg(days_since_prior_order), 2) AS avg_days_since_prior
FROM instacart.orders
GROUP BY order_dow, order_hour_of_day
ORDER BY order_dow, order_hour_of_day
INTO OUTFILE '/data/tableau_order_time_patterns.csv' FORMAT CSVWithNames;

-- Top 100 most-ordered products with reorder rate
SELECT
    p.product_name,
    a.aisle,
    d.department,
    count() AS times_ordered,
    round(sum(op.reordered) / count() * 100, 2) AS reorder_rate_pct
FROM instacart.order_products_prior op
JOIN instacart.products p ON op.product_id = p.product_id
JOIN instacart.aisles a ON p.aisle_id = a.aisle_id
JOIN instacart.departments d ON p.department_id = d.department_id
GROUP BY p.product_name, a.aisle, d.department
ORDER BY times_ordered DESC
LIMIT 100
INTO OUTFILE '/data/tableau_top100_products.csv' FORMAT CSVWithNames;
