-- One row per item on product-funnel events (view_item, add_to_cart, begin_checkout,
-- purchase). Purchase items come only from the deduplicated purchase event.
SELECT
  e.event_id,
  e.event_name,
  e.event_date,
  e.event_ts,
  e.user_pseudo_id,
  e.session_key,
  p.transaction_key,
  item.item_id,
  item.item_name,
  item.item_category,
  item.price_in_usd AS price_usd,
  item.quantity,
  COALESCE(item.item_revenue_in_usd, item.price_in_usd * item.quantity) AS item_revenue_usd
FROM {{ ref('stg_ga4__events') }} AS e
CROSS JOIN UNNEST(e.items) AS item
LEFT JOIN {{ ref('stg_ga4__purchases') }} AS p
  ON p.event_id = e.event_id
WHERE e.event_name IN ('view_item', 'add_to_cart', 'begin_checkout', 'purchase')
  AND (e.event_name != 'purchase' OR p.event_id IS NOT NULL)
