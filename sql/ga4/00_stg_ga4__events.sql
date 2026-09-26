-- One row per GA4 event, flattened.
-- Source: Google's obfuscated GA4 sample (Google Merchandise Store, Nov 2020 - Jan 2021).
-- Placeholders such as '<Other>' and '(not set)' are kept as-is here; later models decide
-- how to treat them, and dq_ga4__placeholder_share reports how common they are.
WITH events AS (
  SELECT
    PARSE_DATE('%Y%m%d', event_date) AS event_date,
    TIMESTAMP_MICROS(event_timestamp) AS event_ts,
    event_timestamp,
    event_name,
    user_pseudo_id,
    user_id,
    {{ event_param('ga_session_id', 'int_value') }} AS ga_session_id,
    {{ event_param('ga_session_number', 'int_value') }} AS ga_session_number,
    {{ event_param('page_location') }} AS page_location,
    {{ event_param('source') }} AS event_source,
    {{ event_param('medium') }} AS event_medium,
    {{ event_param('campaign') }} AS event_campaign,
    device.category AS device_category,
    geo.country AS country,
    -- User-scoped: how GA4 first acquired this user (first-touch).
    traffic_source.source AS first_touch_source,
    traffic_source.medium AS first_touch_medium,
    traffic_source.name AS first_touch_campaign,
    ecommerce.transaction_id AS transaction_id,
    ecommerce.purchase_revenue_in_usd AS purchase_revenue_usd,
    ecommerce.total_item_quantity AS total_item_quantity,
    items
  FROM {{ source_events }}
  WHERE {{ table_suffix }} BETWEEN '{{ params.ga4_start_date }}' AND '{{ params.ga4_end_date }}'
)

SELECT
  -- GA4 has no event id. Identical (user, timestamp, name) rows get a sequence number.
  CONCAT(
    user_pseudo_id, '-', CAST(event_timestamp AS STRING), '-', event_name, '-',
    CAST(ROW_NUMBER() OVER (
      PARTITION BY user_pseudo_id, event_timestamp, event_name ORDER BY event_timestamp
    ) AS STRING)
  ) AS event_id,
  -- ga_session_id is only unique per user, so the session key combines both.
  IF(
    ga_session_id IS NULL, NULL,
    CONCAT(user_pseudo_id, '.', CAST(ga_session_id AS STRING))
  ) AS session_key,
  *
FROM events
