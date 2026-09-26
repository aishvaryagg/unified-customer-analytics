-- Channel and campaign performance over the whole period (session-scoped attribution).
SELECT
  channel_group,
  source,
  medium,
  campaign,
  COUNT(*) AS sessions,
  COUNT(DISTINCT user_pseudo_id) AS users,
  COUNTIF(is_new_user) AS new_user_sessions,
  COUNTIF(reached_purchase) AS converting_sessions,
  SUM(transactions) AS transactions,
  SUM(revenue_usd) AS revenue_usd,
  SAFE_DIVIDE(COUNTIF(reached_purchase), COUNT(*)) AS conversion_rate,
  SAFE_DIVIDE(SUM(revenue_usd), SUM(transactions)) AS avg_order_value_usd,
  SAFE_DIVIDE(SUM(revenue_usd), COUNT(*)) AS revenue_per_session_usd
FROM {{ ref('int_ga4__sessions') }}
GROUP BY channel_group, source, medium, campaign
