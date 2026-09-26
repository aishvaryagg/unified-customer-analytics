"""Run validated SQL in BigQuery (production) or DuckDB (offline tests)."""

from __future__ import annotations

import datetime as dt
import decimal
from typing import TYPE_CHECKING, Any

from sqlglot import exp

from uca.config import Settings

if TYPE_CHECKING:
    import duckdb


def _plain(v: Any) -> Any:
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    return v


class DuckDBExecutor:
    def __init__(self, con: "duckdb.DuckDBPyConnection"):
        self.con = con

    def run(self, query: exp.Expression) -> list[dict]:
        cur = self.con.execute(query.sql(dialect="duckdb"))
        cols = [d[0] for d in cur.description]
        return [{c: _plain(v) for c, v in zip(cols, row)} for row in cur.fetchall()]

    def columns(self, table: str) -> list[tuple[str, str]]:
        return [(r[0], r[1]) for r in self.con.execute(f"DESCRIBE {table}").fetchall()]


class BigQueryExecutor:
    def __init__(self, settings: Settings, client=None):
        from uca.runners import bigquery_client

        self.settings = settings
        self.client = client or bigquery_client(settings)

    def _qualify(self, query: exp.Expression) -> exp.Expression:
        ctes = {cte.alias_or_name for cte in query.find_all(exp.CTE)}
        query = query.copy()
        for table in query.find_all(exp.Table):
            if table.name in ctes and not table.db:
                continue
            table.set("db", exp.to_identifier(self.settings.bq_dataset))
            table.set("catalog", exp.to_identifier(self.settings.gcp_project))
        return query

    def sql(self, query: exp.Expression) -> str:
        return self._qualify(query).sql(dialect="bigquery", identify=True)

    def run(self, query: exp.Expression) -> list[dict]:
        from google.cloud import bigquery

        job_config = bigquery.QueryJobConfig(maximum_bytes_billed=self.settings.bq_max_bytes_billed)
        rows = self.client.query(self.sql(query), job_config=job_config).result()
        return [{k: _plain(v) for k, v in row.items()} for row in rows]

    def columns(self, table: str) -> list[tuple[str, str]]:
        ref = f"{self.settings.gcp_project}.{self.settings.bq_dataset}.{table}"
        return [(f.name, f.field_type) for f in self.client.get_table(ref).schema]
