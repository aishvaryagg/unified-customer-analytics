-- One row per reader: are they still engaging at the end of the impression log?
--
-- The reference point is the last timestamp in the data. N = MIND_DISENGAGED_DAYS.
--   Disengaged            no impressions at all in the last N days
--   Passive               still shown articles in the last N days, but no clicks
--   Engaged               clicked in the last N days
--   Insufficient history  active on only one day, so a gap cannot be told apart from an
--                         occasional reader
WITH reference AS (
  SELECT MAX(impression_ts) AS data_end_ts FROM {{ ref('stg_mind__impressions') }}
),

readers AS (
  SELECT
    user_id,
    MIN(impression_ts) AS first_impression_ts,
    MAX(impression_ts) AS last_impression_ts,
    MAX(IF(clicked, impression_ts, NULL)) AS last_click_ts,
    COUNT(DISTINCT impression_date) AS active_days,
    COUNT(DISTINCT impression_key) AS impressions,
    COUNTIF(clicked) AS clicks
  FROM {{ ref('stg_mind__impression_items') }}
  GROUP BY user_id
),

measured AS (
  SELECT
    r.*,
    TIMESTAMP_DIFF(rp.data_end_ts, r.last_impression_ts, HOUR) AS hours_since_last_impression,
    TIMESTAMP_DIFF(rp.data_end_ts, r.last_click_ts, HOUR) AS hours_since_last_click
  FROM readers AS r
  CROSS JOIN reference AS rp
)

SELECT
  *,
  CASE
    WHEN active_days < 2 THEN 'Insufficient history'
    WHEN hours_since_last_impression > {{ params.mind_disengaged_days }} * 24 THEN 'Disengaged'
    WHEN last_click_ts IS NULL
      OR hours_since_last_click > {{ params.mind_disengaged_days }} * 24 THEN 'Passive'
    ELSE 'Engaged'
  END AS engagement_status
FROM measured
