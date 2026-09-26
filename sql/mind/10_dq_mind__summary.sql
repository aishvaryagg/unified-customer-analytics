-- Data-quality summary for MIND, as a single row. MIND has no revenue or other monetary
-- field, so nothing in this project derives a dollar figure from it.
WITH news AS (
  SELECT
    COUNT(*) AS news_articles,
    COUNTIF(abstract IS NULL) AS news_missing_abstract,
    COUNTIF(category IS NULL) AS news_missing_category
  FROM {{ ref('stg_mind__news') }}
),

impressions AS (
  SELECT
    COUNT(*) AS impressions,
    COUNT(DISTINCT user_id) AS readers,
    COUNTIF(history IS NULL) AS impressions_without_history,
    MIN(impression_ts) AS data_start_ts,
    MAX(impression_ts) AS data_end_ts
  FROM {{ ref('stg_mind__impressions') }}
),

items AS (
  SELECT
    COUNT(*) AS articles_shown,
    COUNTIF(i.clicked) AS clicks,
    COUNTIF(i.clicked IS NULL) AS shown_without_click_label,
    COUNTIF(n.news_id IS NULL) AS shown_missing_from_news
  FROM {{ ref('stg_mind__impression_items') }} AS i
  LEFT JOIN {{ ref('stg_mind__news') }} AS n USING (news_id)
),

history AS (
  SELECT
    COUNT(*) AS history_clicks,
    COUNTIF(n.news_id IS NULL) AS history_missing_from_news
  FROM {{ ref('stg_mind__history') }} AS h
  LEFT JOIN {{ ref('stg_mind__news') }} AS n USING (news_id)
)

SELECT
  *,
  SAFE_DIVIDE(clicks, articles_shown) AS overall_click_through_rate,
  SAFE_DIVIDE(news_missing_abstract, news_articles) AS share_news_missing_abstract,
  SAFE_DIVIDE(shown_missing_from_news, articles_shown) AS share_shown_missing_from_news
FROM news
CROSS JOIN impressions
CROSS JOIN items
CROSS JOIN history
