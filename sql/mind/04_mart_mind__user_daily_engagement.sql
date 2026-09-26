-- One row per reader per day with activity, and a day-over-day engagement label.
--
-- These are engagement measures (clicks), never revenue: MIND has no monetary data.
-- The impression log covers only about a week, so the period is a day, not a week.
--
-- Same safeguard as the GA4 revenue trend: a reader needs at least two distinct active
-- days before any trend is assigned, and all impressions on one day are summed first.
--   Baseline                the reader's first active day
--   Engagement expansion    clicks up by more than TREND_THRESHOLD vs previous active day
--   Engagement contraction  clicks down by more than TREND_THRESHOLD
--   Flat                    anything in between
--   Insufficient history    active on only one day
WITH daily AS (
  SELECT
    i.user_id,
    i.impression_date AS activity_date,
    COUNT(DISTINCT i.impression_key) AS impressions,
    COUNT(*) AS articles_shown,
    COUNTIF(i.clicked) AS clicks,
    COUNT(DISTINCT IF(i.clicked, n.category, NULL)) AS clicked_categories
  FROM {{ ref('stg_mind__impression_items') }} AS i
  LEFT JOIN {{ ref('stg_mind__news') }} AS n USING (news_id)
  GROUP BY i.user_id, i.impression_date
),

sequenced AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY activity_date) AS active_day_number,
    COUNT(*) OVER (PARTITION BY user_id) AS active_days,
    LAG(activity_date) OVER (PARTITION BY user_id ORDER BY activity_date) AS previous_active_date,
    LAG(clicks) OVER (PARTITION BY user_id ORDER BY activity_date) AS previous_clicks
  FROM daily
)

SELECT
  user_id,
  activity_date,
  impressions,
  articles_shown,
  clicks,
  SAFE_DIVIDE(clicks, articles_shown) AS click_through_rate,
  clicked_categories,
  active_day_number,
  active_days,
  previous_active_date,
  previous_clicks,
  SAFE_DIVIDE(clicks - previous_clicks, previous_clicks) AS clicks_change_pct,
  CASE
    WHEN active_days < 2 THEN 'Insufficient history'
    WHEN active_day_number = 1 THEN 'Baseline'
    WHEN previous_clicks = 0 AND clicks > 0 THEN 'Engagement expansion'
    WHEN SAFE_DIVIDE(clicks - previous_clicks, previous_clicks)
      > {{ params.trend_threshold }} THEN 'Engagement expansion'
    WHEN SAFE_DIVIDE(clicks - previous_clicks, previous_clicks)
      < -{{ params.trend_threshold }} THEN 'Engagement contraction'
    ELSE 'Flat'
  END AS trend
FROM sequenced
