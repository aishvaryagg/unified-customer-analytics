-- One row per news article. The same article can appear in the train and dev files;
-- one copy is kept. An empty abstract becomes NULL.
SELECT
  news_id,
  NULLIF(category, '') AS category,
  NULLIF(subcategory, '') AS subcategory,
  title,
  NULLIF(abstract, '') AS abstract,
  NULLIF(url, '') AS url,
  NULLIF(title_entities, '') AS title_entities,
  NULLIF(abstract_entities, '') AS abstract_entities
FROM {{ ref('mind_raw_news') }}
WHERE news_id IS NOT NULL AND news_id != ''
QUALIFY ROW_NUMBER() OVER (PARTITION BY news_id ORDER BY split DESC) = 1
