-- One row per user per week in which they bought something, with a week-over-week label.
--
-- Safeguard: a user must have purchased in at least two distinct weeks before any trend
-- is assigned. Several purchases in the same week (or on the same day) are summed into
-- that week first, so they can never be mistaken for a trend.
--
-- Labels, comparing a week to the user's previous purchasing week:
--   Baseline              the user's first purchasing week
--   Expansion             revenue up by more than TREND_THRESHOLD
--   Contraction           revenue down by more than TREND_THRESHOLD
--   Flat                  anything in between
--   Insufficient history  the user purchased in only one week
WITH weekly AS (
  SELECT
    user_pseudo_id,
    purchase_week AS week_start,
    COUNT(*) AS transactions,
    SUM(COALESCE(revenue_usd, 0)) AS revenue_usd
  FROM {{ ref('stg_ga4__purchases') }}
  GROUP BY user_pseudo_id, purchase_week
),

sequenced AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY user_pseudo_id ORDER BY week_start) AS active_week_number,
    COUNT(*) OVER (PARTITION BY user_pseudo_id) AS active_weeks,
    LAG(week_start) OVER (PARTITION BY user_pseudo_id ORDER BY week_start) AS previous_active_week,
    LAG(revenue_usd) OVER (PARTITION BY user_pseudo_id ORDER BY week_start) AS previous_revenue_usd
  FROM weekly
)

SELECT
  user_pseudo_id,
  week_start,
  transactions,
  revenue_usd,
  active_week_number,
  active_weeks,
  previous_active_week,
  previous_revenue_usd,
  SAFE_DIVIDE(revenue_usd - previous_revenue_usd, previous_revenue_usd) AS revenue_change_pct,
  CASE
    WHEN active_weeks < 2 THEN 'Insufficient history'
    WHEN active_week_number = 1 THEN 'Baseline'
    WHEN previous_revenue_usd = 0 AND revenue_usd > 0 THEN 'Expansion'
    WHEN SAFE_DIVIDE(revenue_usd - previous_revenue_usd, previous_revenue_usd)
      > {{ params.trend_threshold }} THEN 'Expansion'
    WHEN SAFE_DIVIDE(revenue_usd - previous_revenue_usd, previous_revenue_usd)
      < -{{ params.trend_threshold }} THEN 'Contraction'
    ELSE 'Flat'
  END AS trend
FROM sequenced
