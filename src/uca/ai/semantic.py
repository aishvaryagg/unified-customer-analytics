"""Semantic search over MIND article text, using BigQuery ML embeddings and VECTOR_SEARCH.

One-time setup in BigQuery (see docs/ai.md): a Vertex AI connection and a remote
embedding model named MIND_EMBEDDING_MODEL in BQ_DATASET. Then `uca build-embeddings`
embeds every article's title + abstract into ``mind_article_embeddings``. A search
embeds the question with the same model and returns the nearest articles, with how often
each was shown and clicked in the impression log.
"""

from __future__ import annotations

from uca.config import Settings

EMBEDDINGS_SQL = """
CREATE OR REPLACE TABLE `{project}.{dataset}.mind_article_embeddings` AS
SELECT *
FROM ML.GENERATE_EMBEDDING(
  MODEL `{project}.{dataset}.{model}`,
  (
    SELECT
      news_id, category, subcategory, title, abstract,
      CONCAT(title, '. ', COALESCE(abstract, '')) AS content
    FROM `{project}.{dataset}.stg_mind__news`
  ),
  STRUCT(TRUE AS flatten_json_output, 'RETRIEVAL_DOCUMENT' AS task_type)
)
WHERE ARRAY_LENGTH(ml_generate_embedding_result) > 0
"""

SEARCH_SQL = """
SELECT
  search.base.news_id AS news_id,
  search.base.category AS category,
  search.base.subcategory AS subcategory,
  search.base.title AS title,
  search.base.abstract AS abstract,
  search.distance AS distance,
  COALESCE(engagement.times_shown, 0) AS times_shown,
  COALESCE(engagement.clicks, 0) AS clicks
FROM VECTOR_SEARCH(
  TABLE `{project}.{dataset}.mind_article_embeddings`,
  'ml_generate_embedding_result',
  (
    SELECT ml_generate_embedding_result
    FROM ML.GENERATE_EMBEDDING(
      MODEL `{project}.{dataset}.{model}`,
      (SELECT @query AS content),
      STRUCT(TRUE AS flatten_json_output, 'RETRIEVAL_QUERY' AS task_type)
    )
  ),
  top_k => {top_k},
  distance_type => 'COSINE'
) AS search
LEFT JOIN (
  SELECT news_id, COUNT(*) AS times_shown, COUNTIF(clicked) AS clicks
  FROM `{project}.{dataset}.stg_mind__impression_items`
  GROUP BY news_id
) AS engagement
  ON engagement.news_id = search.base.news_id
ORDER BY distance
"""


def _names(settings: Settings) -> dict:
    return {
        "project": settings.gcp_project,
        "dataset": settings.bq_dataset,
        "model": settings.mind_embedding_model,
    }


def build_embeddings(settings: Settings, client=None, log=print) -> None:
    from uca.runners import bigquery_client

    client = client or bigquery_client(settings)
    job = client.query(EMBEDDINGS_SQL.format(**_names(settings)))
    job.result()
    log(f"built mind_article_embeddings: {(job.total_bytes_processed or 0) / 1e9:.2f} GB processed")


class BigQuerySemanticSearch:
    def __init__(self, settings: Settings, client=None):
        from uca.runners import bigquery_client

        self.settings = settings
        self.client = client or bigquery_client(settings)

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        from google.cloud import bigquery

        sql = SEARCH_SQL.format(top_k=int(top_k), **_names(self.settings))
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("query", "STRING", query)],
            maximum_bytes_billed=self.settings.bq_max_bytes_billed,
        )
        return [dict(row.items()) for row in self.client.query(sql, job_config=job_config).result()]
