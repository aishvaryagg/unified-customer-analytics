-- One row per article in a reader's click history: clicks made *before* the impression
-- log starts, ordered oldest to newest in the raw data. recency_rank 1 = most recent.
-- The history carries no timestamps, so it is treated as one "before" period.
WITH latest AS (
  SELECT user_id, history
  FROM {{ ref('stg_mind__impressions') }}
  WHERE history IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY user_id ORDER BY impression_ts DESC, impression_key DESC
  ) = 1
)

SELECT
  user_id,
  news_id,
  -- Positions are used only for ordering (BigQuery counts from 0, DuckDB from 1).
  ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY position DESC) AS recency_rank
FROM latest
CROSS JOIN UNNEST(SPLIT(history, ' ')) AS news_id WITH OFFSET AS position
WHERE news_id != ''
