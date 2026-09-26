-- One row per purchasing user: their overall revenue and most recent trend label.
SELECT
  user_pseudo_id,
  active_weeks,
  MIN(week_start) OVER (PARTITION BY user_pseudo_id) AS first_purchase_week,
  week_start AS last_purchase_week,
  SUM(transactions) OVER (PARTITION BY user_pseudo_id) AS transactions,
  SUM(revenue_usd) OVER (PARTITION BY user_pseudo_id) AS revenue_usd,
  revenue_usd AS last_week_revenue_usd,
  previous_revenue_usd,
  revenue_change_pct AS last_revenue_change_pct,
  trend AS latest_trend
FROM {{ ref('mart_user_weekly_revenue') }}
WHERE TRUE
QUALIFY ROW_NUMBER() OVER (PARTITION BY user_pseudo_id ORDER BY week_start DESC) = 1
