-- Daily e-commerce funnel by channel and device. Each stage counts sessions that fired
-- that event at least once; step rates compare each stage to the one before it.
SELECT
  session_date,
  channel_group,
  device_category,
  COUNT(*) AS sessions,
  COUNTIF(reached_view_item) AS view_item_sessions,
  COUNTIF(reached_add_to_cart) AS add_to_cart_sessions,
  COUNTIF(reached_checkout) AS checkout_sessions,
  COUNTIF(reached_purchase) AS purchase_sessions,
  SAFE_DIVIDE(COUNTIF(reached_view_item), COUNT(*)) AS view_item_rate,
  SAFE_DIVIDE(COUNTIF(reached_add_to_cart), COUNTIF(reached_view_item)) AS view_to_cart_rate,
  SAFE_DIVIDE(COUNTIF(reached_checkout), COUNTIF(reached_add_to_cart)) AS cart_to_checkout_rate,
  SAFE_DIVIDE(COUNTIF(reached_purchase), COUNTIF(reached_checkout)) AS checkout_to_purchase_rate,
  SAFE_DIVIDE(COUNTIF(reached_purchase), COUNT(*)) AS session_conversion_rate
FROM {{ ref('int_ga4__sessions') }}
GROUP BY session_date, channel_group, device_category
