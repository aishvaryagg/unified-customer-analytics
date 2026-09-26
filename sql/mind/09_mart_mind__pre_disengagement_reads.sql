-- What Disengaged and Passive readers were reading before they dropped off: their 10 most
-- recent clicked articles, with title and abstract. This is the input for the AI pattern
-- analysis (semantic search and summaries) added later.
-- Clicks from the impression log come first (newest first), then history clicks.
WITH at_risk AS (
  SELECT user_id, engagement_status
  FROM {{ ref('mart_mind__user_disengagement') }}
  WHERE engagement_status IN ('Disengaged', 'Passive')
),

reads AS (
  SELECT user_id, news_id, impression_ts AS clicked_at, 'impression_log' AS source,
    0 AS source_order, NULL AS recency_rank
  FROM {{ ref('stg_mind__impression_items') }}
  WHERE clicked
  UNION ALL
  SELECT user_id, news_id, NULL, 'history', 1, recency_rank
  FROM {{ ref('stg_mind__history') }}
),

ranked AS (
  SELECT
    a.user_id,
    a.engagement_status,
    r.news_id,
    r.clicked_at,
    r.source,
    ROW_NUMBER() OVER (
      PARTITION BY a.user_id
      ORDER BY r.source_order, r.clicked_at DESC, r.recency_rank, r.news_id
    ) AS read_rank
  FROM at_risk AS a
  JOIN reads AS r USING (user_id)
)

SELECT
  r.user_id,
  r.engagement_status,
  r.read_rank,
  r.news_id,
  r.clicked_at,
  r.source,
  n.category,
  n.subcategory,
  n.title,
  n.abstract
FROM ranked AS r
LEFT JOIN {{ ref('stg_mind__news') }} AS n USING (news_id)
WHERE r.read_rank <= 10
