"""Build the models in BigQuery (production) or DuckDB (offline tests)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from uca.config import Settings
from uca.sql import GROUPS, Model, discover_models, render, table_ref, to_duckdb

if TYPE_CHECKING:
    import duckdb


def select_models(groups: Iterable[str], names: Iterable[str] | None = None) -> list[Model]:
    """Models from the given groups in build order, optionally only the named ones."""
    models = [m for group in GROUPS if group in set(groups) for m in discover_models(group)]
    if not names:
        return models
    wanted = set(names)
    unknown = wanted - {m.name for m in models}
    if unknown:
        raise ValueError(f"Unknown model(s): {', '.join(sorted(unknown))}")
    return [m for m in models if m.name in wanted]


def compile_bigquery(
    settings: Settings, out_dir: Path, groups: Iterable[str] = GROUPS, names: Iterable[str] | None = None
) -> list[Path]:
    """Write each model's rendered BigQuery SQL to ``out_dir/<group>/`` for review."""
    written = []
    for model in select_models(groups, names):
        path = out_dir / model.path.parent.name / f"{model.name}.sql"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(model, "bigquery", settings))
        written.append(path)
    return written


def bigquery_client(settings: Settings):
    from google.cloud import bigquery

    if not settings.gcp_project:
        raise ValueError("GCP_PROJECT must be set (see .env.example)")
    client = bigquery.Client(project=settings.gcp_project, location=settings.bq_location)
    dataset = bigquery.Dataset(f"{settings.gcp_project}.{settings.bq_dataset}")
    dataset.location = settings.bq_location
    client.create_dataset(dataset, exists_ok=True)
    return client


def build_bigquery(
    settings: Settings, groups: Iterable[str] = GROUPS, names: Iterable[str] | None = None, log=print
) -> None:
    """Create or replace each model as a table in ``GCP_PROJECT.BQ_DATASET``."""
    from google.cloud import bigquery

    client = bigquery_client(settings)
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=settings.bq_max_bytes_billed)
    for model in select_models(groups, names):
        target = table_ref(model.name, "bigquery", settings)
        sql = f"CREATE OR REPLACE TABLE {target} AS\n{render(model, 'bigquery', settings)}"
        job = client.query(sql, job_config=job_config)
        job.result()
        gb = (job.total_bytes_processed or 0) / 1e9
        log(f"built {model.name}: {gb:.2f} GB processed")


def build_duckdb(
    con: "duckdb.DuckDBPyConnection",
    settings: Settings,
    group: str = "ga4",
    source_table: str = "ga4_events",
) -> list[str]:
    """Build one group's models into a DuckDB connection. Used by the offline tests."""
    built = []
    for model in discover_models(group):
        sql = to_duckdb(render(model, "duckdb", settings, source_table=source_table))
        con.execute(f"CREATE OR REPLACE TABLE {model.name} AS {sql}")
        built.append(model.name)
    return built
