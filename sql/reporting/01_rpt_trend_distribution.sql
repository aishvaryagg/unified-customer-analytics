-- The common framework: how many GA4 customers and MIND readers are expanding,
-- contracting or flat, using the same labels and the same "at least two active periods"
-- safeguard. GA4 compares weeks of revenue; MIND compares days of clicks. The two are
-- reported side by side and never merged.
WITH labelled AS (
  SELECT
    'GA4' AS source,
    'Customers' AS population,
    'Revenue, week over week' AS measure,
    latest_trend AS trend_label
  FROM {{ ref('mart_user_revenue_trend') }}
  UNION ALL
  SELECT 'MIND', 'Readers', 'Clicks, day over day', latest_trend
  FROM {{ ref('mart_mind__user_engagement_trend') }}
),

grouped AS (
  SELECT
    source,
    population,
    measure,
    CASE
      WHEN trend_label IN ('Expansion', 'Engagement expansion') THEN 'Expansion'
      WHEN trend_label IN ('Contraction', 'Engagement contraction') THEN 'Contraction'
      ELSE trend_label
    END AS trend,
    trend_label,
    COUNT(*) AS people
  FROM labelled
  GROUP BY source, population, measure, trend_label
)

SELECT
  *,
  CASE trend WHEN 'Expansion' THEN 1 WHEN 'Flat' THEN 2 WHEN 'Contraction' THEN 3 ELSE 4 END AS trend_order,
  SAFE_DIVIDE(people, SUM(people) OVER (PARTITION BY source)) AS share
FROM grouped
