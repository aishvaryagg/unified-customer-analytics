-- One row per session: where it came from, how far it got in the funnel, what it earned.
--
-- Session source/medium/campaign come from the first event in the session that carries
-- them. A session with none is treated as direct, which is how GA4 labels traffic with
-- no campaign information. (GA4's own reports go further and credit such sessions to the
-- user's last non-direct source; that is not replicated here.)
WITH events AS (
  SELECT *
  FROM {{ ref('stg_ga4__events') }}
  WHERE session_key IS NOT NULL
),

first_event AS (
  SELECT session_key, user_pseudo_id, ga_session_id, event_ts, event_date, device_category, country
  FROM events
  WHERE TRUE
  QUALIFY ROW_NUMBER() OVER (PARTITION BY session_key ORDER BY event_ts, event_id) = 1
),

session_source AS (
  SELECT session_key, event_source, event_medium, event_campaign
  FROM events
  WHERE event_source IS NOT NULL OR event_medium IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY session_key ORDER BY event_ts, event_id) = 1
),

activity AS (
  SELECT
    session_key,
    MAX(ga_session_number) AS session_number,
    COUNT(*) AS events,
    COUNTIF(event_name = 'page_view') AS page_views,
    LOGICAL_OR(event_name = 'view_item') AS reached_view_item,
    LOGICAL_OR(event_name = 'add_to_cart') AS reached_add_to_cart,
    LOGICAL_OR(event_name = 'begin_checkout') AS reached_checkout
  FROM events
  GROUP BY session_key
),

revenue AS (
  SELECT
    session_key,
    COUNT(*) AS transactions,
    SUM(revenue_usd) AS revenue_usd
  FROM {{ ref('stg_ga4__purchases') }}
  WHERE session_key IS NOT NULL
  GROUP BY session_key
),

sessions AS (
  SELECT
    f.session_key,
    f.user_pseudo_id,
    f.ga_session_id,
    a.session_number,
    a.session_number = 1 AS is_new_user,
    f.event_ts AS session_start_ts,
    f.event_date AS session_date,  -- GA4's reporting-time-zone date, as in GA4 reports
    {{ week_start('f.event_date') }} AS session_week,
    {{ clean_label('f.device_category') }} AS device_category,
    {{ clean_label('f.country') }} AS country,
    COALESCE(s.event_source, '(direct)') AS source,
    COALESCE(s.event_medium, '(none)') AS medium,
    {{ clean_label('s.event_campaign') }} AS campaign,
    a.events,
    a.page_views,
    a.reached_view_item,
    a.reached_add_to_cart,
    a.reached_checkout,
    r.transactions IS NOT NULL AS reached_purchase,
    COALESCE(r.transactions, 0) AS transactions,
    COALESCE(r.revenue_usd, 0) AS revenue_usd
  FROM first_event AS f
  JOIN activity AS a USING (session_key)
  LEFT JOIN session_source AS s USING (session_key)
  LEFT JOIN revenue AS r USING (session_key)
)

SELECT
  *,
  {{ channel_group('source', 'medium') }} AS channel_group
FROM sessions
