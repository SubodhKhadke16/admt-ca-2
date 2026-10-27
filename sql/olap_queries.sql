-- Tourism Analytics: 8 OLAP/analytical queries
-- Run after executing python tourism.py.

-- 1. Roll-up: tourist visits by year
SELECT d.year, SUM(f.visitors) AS total_visitors
FROM fact_tourism f JOIN dim_date d USING(date_key)
GROUP BY d.year ORDER BY d.year;

-- 2. Drill-down: tourist visits by month
SELECT d.year, d.month, SUM(f.visitors) AS total_visitors
FROM fact_tourism f JOIN dim_date d USING(date_key)
GROUP BY d.year, d.month ORDER BY d.year, d.month;

-- 3. Slice: winter visitors by destination
SELECT x.destination, SUM(f.visitors) AS visitors
FROM fact_tourism f JOIN dim_date d USING(date_key)
JOIN dim_destination x USING(destination_key)
WHERE d.season='Winter'
GROUP BY x.destination ORDER BY visitors DESC;

-- 4. Dice: domestic expenditure in summer and winter
SELECT x.destination, SUM(f.expenditure) AS spending
FROM fact_tourism f JOIN dim_date d USING(date_key)
JOIN dim_destination x USING(destination_key)
JOIN dim_visitor v USING(visitor_category_key)
WHERE d.season IN ('Summer','Winter') AND v.category='Domestic'
GROUP BY x.destination ORDER BY spending DESC;

-- 5. Pivot: domestic versus international visitors
SELECT x.destination,
 SUM(CASE WHEN v.category='Domestic' THEN f.visitors ELSE 0 END) AS domestic_visitors,
 SUM(CASE WHEN v.category='International' THEN f.visitors ELSE 0 END) AS international_visitors
FROM fact_tourism f JOIN dim_destination x USING(destination_key)
JOIN dim_visitor v USING(visitor_category_key)
GROUP BY x.destination ORDER BY x.destination;

-- 6. Aggregation: expenditure and visitors by destination
SELECT x.destination, SUM(f.expenditure) AS total_expenditure,
 ROUND(AVG(f.expenditure),2) AS average_record_expenditure,
 SUM(f.visitors) AS total_visitors
FROM fact_tourism f JOIN dim_destination x USING(destination_key)
GROUP BY x.destination ORDER BY total_expenditure DESC;

-- 7. Additional query: hotel revenue by destination
SELECT x.destination, ROUND(SUM(f.hotel_revenue),2) AS hotel_revenue
FROM fact_tourism f JOIN dim_destination x USING(destination_key)
GROUP BY x.destination ORDER BY hotel_revenue DESC;

-- 8. Additional query: visitors by destination type
SELECT x.destination_type, SUM(f.visitors) AS total_visitors
FROM fact_tourism f JOIN dim_destination x USING(destination_key)
GROUP BY x.destination_type ORDER BY total_visitors DESC;
