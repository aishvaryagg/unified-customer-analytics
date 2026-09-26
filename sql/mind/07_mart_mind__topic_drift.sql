-- Topic drift: is a reader moving away from a category they used to read?
--
-- Compares each reader's category mix in two periods:
--   past     clicks in their history (before the impression log)
--   current  clicks during the impression log
-- One row per reader x category. share_change is in share points (0.25 = 25 points).
--   Drifting away     share fell by at least MIND_DRIFT_THRESHOLD
--   Growing interest  share rose by at least MIND_DRIFT_THRESHOLD
--   Stable            otherwise
-- drift_score (0-1) is how different the reader's two mixes are overall
-- (half the sum of absolute share changes). Only readers with at least MIND_MIN_CLICKS
-- clicks in both periods are scored.
WITH past AS (
  SELECT h.user_id, COALESCE(n.category, '(unknown)') AS category, COUNT(*) AS clicks
  FROM {{ ref('stg_mind__history') }} AS h
  LEFT JOIN {{ ref('stg_mind__news') }} AS n USING (news_id)
  GROUP BY 1, 2
),

current_period AS (
  SELECT i.user_id, COALESCE(n.category, '(unknown)') AS category, COUNT(*) AS clicks
  FROM {{ ref('stg_mind__impression_items') }} AS i
  LEFT JOIN {{ ref('stg_mind__news') }} AS n USING (news_id)
  WHERE i.clicked
  GROUP BY 1, 2
),

combined AS (
  SELECT
    user_id,
    category,
    COALESCE(p.clicks, 0) AS past_clicks,
    COALESCE(c.clicks, 0) AS current_clicks
  FROM past AS p
  FULL OUTER JOIN current_period AS c USING (user_id, category)
),

totals AS (
  SELECT
    *,
    SUM(past_clicks) OVER (PARTITION BY user_id) AS user_past_clicks,
    SUM(current_clicks) OVER (PARTITION BY user_id) AS user_current_clicks
  FROM combined
),

shares AS (
  SELECT
    *,
    SAFE_DIVIDE(past_clicks, user_past_clicks) AS past_share,
    SAFE_DIVIDE(current_clicks, user_current_clicks) AS current_share
  FROM totals
  WHERE user_past_clicks >= {{ params.mind_min_clicks }}
    AND user_current_clicks >= {{ params.mind_min_clicks }}
)

SELECT
  user_id,
  category,
  past_clicks,
  current_clicks,
  user_past_clicks,
  user_current_clicks,
  past_share,
  current_share,
  current_share - past_share AS share_change,
  0.5 * SUM(ABS(current_share - past_share)) OVER (PARTITION BY user_id) AS drift_score,
  CASE
    WHEN current_share - past_share <= -{{ params.mind_drift_threshold }} THEN 'Drifting away'
    WHEN current_share - past_share >= {{ params.mind_drift_threshold }} THEN 'Growing interest'
    ELSE 'Stable'
  END AS direction
FROM shares
