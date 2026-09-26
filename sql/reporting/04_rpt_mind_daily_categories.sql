-- Daily MIND engagement by content category, for time-series charts. The six categories
-- with the most clicks keep their name; the rest are folded into 'Other'.
WITH shown AS (
  SELECT
    i.impression_date,
    i.user_id,
    i.clicked,
    COALESCE(n.category, '(unknown)') AS category
  FROM {{ ref('stg_mind__impression_items') }} AS i
  LEFT JOIN {{ ref('stg_mind__news') }} AS n USING (news_id)
),

category_rank AS (
  SELECT
    category,
    ROW_NUMBER() OVER (ORDER BY COUNTIF(clicked) DESC, COUNT(*) DESC, category) AS click_rank
  FROM shown
  GROUP BY category
),

folded AS (
  SELECT
    s.impression_date AS activity_date,
    IF(r.click_rank <= 6, s.category, 'Other') AS category_group,
    s.user_id,
    s.clicked
  FROM shown AS s
  JOIN category_rank AS r USING (category)
)

SELECT
  activity_date,
  category_group AS category,
  COUNT(*) AS times_shown,
  COUNTIF(clicked) AS clicks,
  SAFE_DIVIDE(COUNTIF(clicked), COUNT(*)) AS click_through_rate,
  COUNT(DISTINCT user_id) AS readers
FROM folded
GROUP BY activity_date, category_group
