-- One row per reader: totals over the impression log and their most recent trend label.
SELECT
  user_id,
  active_days,
  MIN(activity_date) OVER (PARTITION BY user_id) AS first_active_date,
  activity_date AS last_active_date,
  SUM(impressions) OVER (PARTITION BY user_id) AS impressions,
  SUM(articles_shown) OVER (PARTITION BY user_id) AS articles_shown,
  SUM(clicks) OVER (PARTITION BY user_id) AS clicks,
  SAFE_DIVIDE(
    SUM(clicks) OVER (PARTITION BY user_id),
    SUM(articles_shown) OVER (PARTITION BY user_id)
  ) AS click_through_rate,
  clicks AS last_day_clicks,
  previous_clicks,
  clicks_change_pct AS last_clicks_change_pct,
  trend AS latest_trend
FROM {{ ref('mart_mind__user_daily_engagement') }}
WHERE TRUE
QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY activity_date DESC) = 1
