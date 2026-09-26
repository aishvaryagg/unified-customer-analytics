-- Data-quality disclosure: how often each field used in this project holds a placeholder
-- instead of a real value. Google obfuscated this public sample, so some values are
-- replaced with '<Other>' or '(data deleted)', and GA4 itself writes '(not set)'.
WITH checks AS (
  SELECT 'events' AS grain, 'event_params.source' AS field, event_source AS value
  FROM {{ ref('stg_ga4__events') }}
  WHERE event_source IS NOT NULL
  UNION ALL
  SELECT 'events', 'event_params.medium', event_medium
  FROM {{ ref('stg_ga4__events') }} WHERE event_medium IS NOT NULL
  UNION ALL
  SELECT 'events', 'event_params.campaign', event_campaign
  FROM {{ ref('stg_ga4__events') }} WHERE event_campaign IS NOT NULL
  UNION ALL
  SELECT 'events', 'traffic_source.source', first_touch_source
  FROM {{ ref('stg_ga4__events') }}
  UNION ALL
  SELECT 'events', 'traffic_source.medium', first_touch_medium
  FROM {{ ref('stg_ga4__events') }}
  UNION ALL
  SELECT 'purchases', 'ecommerce.transaction_id', transaction_id
  FROM {{ ref('stg_ga4__events') }} WHERE event_name = 'purchase'
  UNION ALL
  SELECT 'items', 'items.item_name', item_name
  FROM {{ ref('stg_ga4__items') }}
  UNION ALL
  SELECT 'items', 'items.item_category', item_category
  FROM {{ ref('stg_ga4__items') }}
)

SELECT
  grain,
  field,
  COUNT(*) AS total_rows,
  COUNTIF(NOT {{ is_known('value') }}) AS placeholder_rows,
  COUNTIF(value IN ('<Other>', '(data deleted)')) AS obfuscated_rows,
  SAFE_DIVIDE(COUNTIF(NOT {{ is_known('value') }}), COUNT(*)) AS placeholder_share
FROM checks
GROUP BY grain, field
