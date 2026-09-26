-- Revenue credited to each channel under three attribution models (long format):
--   first_touch  the channel that first acquired the user (GA4 traffic_source)
--   last_touch   the channel of the session the purchase happened in
--   linear       split evenly across the user's sessions up to and including that one
-- Every model credits the same total revenue, so channels can be compared directly.
WITH purchases AS (
  SELECT p.transaction_key, p.user_pseudo_id, p.purchase_ts, p.revenue_usd, s.channel_group
  FROM {{ ref('stg_ga4__purchases') }} AS p
  JOIN {{ ref('int_ga4__sessions') }} AS s USING (session_key)
),

first_touch AS (
  SELECT
    user_pseudo_id,
    {{ channel_group('first_touch_source', 'first_touch_medium') }} AS channel_group
  FROM {{ ref('stg_ga4__events') }}
  WHERE TRUE
  QUALIFY ROW_NUMBER() OVER (PARTITION BY user_pseudo_id ORDER BY event_ts, event_id) = 1
),

linear_touches AS (
  SELECT
    p.transaction_key,
    p.revenue_usd,
    s.channel_group,
    COUNT(*) OVER (PARTITION BY p.transaction_key) AS touches
  FROM purchases AS p
  JOIN {{ ref('int_ga4__sessions') }} AS s
    ON s.user_pseudo_id = p.user_pseudo_id
   AND s.session_start_ts <= p.purchase_ts
),

credited AS (
  SELECT 'first_touch' AS attribution_model, f.channel_group, 1.0 AS conversions, p.revenue_usd
  FROM purchases AS p
  JOIN first_touch AS f USING (user_pseudo_id)
  UNION ALL
  SELECT 'last_touch', channel_group, 1.0, revenue_usd
  FROM purchases
  UNION ALL
  SELECT 'linear', channel_group, 1.0 / touches, revenue_usd / touches
  FROM linear_touches
)

SELECT
  attribution_model,
  channel_group,
  SUM(conversions) AS conversions,
  SUM(revenue_usd) AS revenue_usd
FROM credited
GROUP BY attribution_model, channel_group
