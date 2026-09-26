-- One row per impression: one page load where the reader was shown a list of articles.
-- impression_id restarts in each split, so the key combines split and id.
-- MIND timestamps have no time zone; they are used as given.
SELECT
  CONCAT(split, '-', impression_id) AS impression_key,
  split,
  user_id,
  PARSE_TIMESTAMP('%m/%d/%Y %I:%M:%S %p', time) AS impression_ts,
  DATE(PARSE_TIMESTAMP('%m/%d/%Y %I:%M:%S %p', time)) AS impression_date,
  NULLIF(history, '') AS history,
  impressions
FROM {{ ref('mind_raw_behaviors') }}
WHERE user_id IS NOT NULL AND user_id != ''
