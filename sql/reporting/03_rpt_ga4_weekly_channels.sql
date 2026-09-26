-- Weekly GA4 performance by channel, for time-series charts. The five channels with the
-- most revenue keep their name; the rest are folded into 'Other' so a chart never needs
-- more than six colors.
WITH channel_rank AS (
  SELECT
    channel_group,
    ROW_NUMBER() OVER (ORDER BY SUM(revenue_usd) DESC, COUNT(*) DESC, channel_group) AS revenue_rank
  FROM {{ ref('int_ga4__sessions') }}
  GROUP BY channel_group
),

folded AS (
  SELECT
    s.session_week AS week_start,
    IF(r.revenue_rank <= 5, s.channel_group, 'Other') AS channel,
    s.reached_purchase,
    s.transactions,
    s.revenue_usd
  FROM {{ ref('int_ga4__sessions') }} AS s
  JOIN channel_rank AS r USING (channel_group)
)

SELECT
  week_start,
  channel,
  COUNT(*) AS sessions,
  COUNTIF(reached_purchase) AS converting_sessions,
  SUM(transactions) AS transactions,
  SUM(revenue_usd) AS revenue_usd,
  SAFE_DIVIDE(COUNTIF(reached_purchase), COUNT(*)) AS conversion_rate
FROM folded
GROUP BY week_start, channel
