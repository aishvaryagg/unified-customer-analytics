-- Content performance by category and subcategory: how often articles were shown and
-- clicked during the impression log, plus clicks from readers' earlier history.
-- Articles missing from news.tsv are grouped under '(unknown)'.
WITH shown AS (
  SELECT
    COALESCE(n.category, '(unknown)') AS category,
    COALESCE(n.subcategory, '(unknown)') AS subcategory,
    COUNT(DISTINCT i.news_id) AS articles_shown_distinct,
    COUNT(*) AS times_shown,
    COUNTIF(i.clicked) AS clicks,
    COUNT(DISTINCT i.user_id) AS readers_shown,
    COUNT(DISTINCT IF(i.clicked, i.user_id, NULL)) AS readers_clicked
  FROM {{ ref('stg_mind__impression_items') }} AS i
  LEFT JOIN {{ ref('stg_mind__news') }} AS n USING (news_id)
  GROUP BY 1, 2
),

history AS (
  SELECT
    COALESCE(n.category, '(unknown)') AS category,
    COALESCE(n.subcategory, '(unknown)') AS subcategory,
    COUNT(*) AS history_clicks
  FROM {{ ref('stg_mind__history') }} AS h
  LEFT JOIN {{ ref('stg_mind__news') }} AS n USING (news_id)
  GROUP BY 1, 2
)

SELECT
  category,
  subcategory,
  COALESCE(s.articles_shown_distinct, 0) AS articles_shown_distinct,
  COALESCE(s.times_shown, 0) AS times_shown,
  COALESCE(s.clicks, 0) AS clicks,
  SAFE_DIVIDE(s.clicks, s.times_shown) AS click_through_rate,
  COALESCE(s.readers_shown, 0) AS readers_shown,
  COALESCE(s.readers_clicked, 0) AS readers_clicked,
  COALESCE(h.history_clicks, 0) AS history_clicks
FROM shown AS s
FULL OUTER JOIN history AS h USING (category, subcategory)
