-- One row per transaction. GA4 can log the same purchase more than once, so events are
-- deduplicated on transaction_id (earliest event kept). A purchase with a missing or
-- placeholder transaction_id is treated as its own transaction.
SELECT
  IF({{ is_known('transaction_id') }}, transaction_id, event_id) AS transaction_key,
  event_id,
  user_pseudo_id,
  session_key,
  event_ts AS purchase_ts,
  event_date AS purchase_date,
  {{ week_start('event_date') }} AS purchase_week,
  purchase_revenue_usd AS revenue_usd,
  total_item_quantity
FROM {{ ref('stg_ga4__events') }}
WHERE event_name = 'purchase'
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY IF({{ is_known('transaction_id') }}, transaction_id, event_id)
  ORDER BY event_ts, event_id
) = 1
