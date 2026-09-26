"""Build the models in BigQuery (production) or DuckDB (offline tests)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from uca.config import Settings
from uca.sql import GA4_MODELS_DIR, Model, discover_models, render, table_ref, to_duckdb

if TYPE_CHECKING:
    import duckdb


def select_models(models: list[Model], names: Iterable[str] | None) -> list[Model]:
    if not names:
        return models
    wanted = set(names)
    unknown = wanted - {m.name for m in models}
    if unknown:
        raise ValueError(f"Unknown model(s): {', '.join(sorted(unknown))}")
    return [m for m in models if m.name in wanted]


def compile_bigquery(settings: Settings, out_dir: Path, names: Iterable[str] | None = None) -> list[Path]:
    """Write each model's rendered BigQuery SQL to ``out_dir`` for review."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for model in select_models(discover_models(GA4_MODELS_DIR), names):
        path = out_dir / f"{model.name}.sql"
        path.write_text(render(model, "bigquery", settings))
        written.append(path)
    return written


def build_bigquery(settings: Settings, names: Iterable[str] | None = None, log=print) -> None:
    """Create or replace each model as a table in ``GCP_PROJECT.BQ_DATASET``."""
    from google.cloud import bigquery

    client = bigquery.Client(project=settings.gcp_project, location=settings.bq_location)
    dataset = bigquery.Dataset(f"{settings.gcp_project}.{settings.bq_dataset}")
    dataset.location = settings.bq_location
    client.create_dataset(dataset, exists_ok=True)

    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=settings.bq_max_bytes_billed)
    for model in select_models(discover_models(GA4_MODELS_DIR), names):
        target = table_ref(model.name, "bigquery", settings)
        sql = f"CREATE OR REPLACE TABLE {target} AS\n{render(model, 'bigquery', settings)}"
        job = client.query(sql, job_config=job_config)
        job.result()
        gb = (job.total_bytes_processed or 0) / 1e9
        log(f"built {model.name}: {gb:.2f} GB processed")


def build_duckdb(
    con: "duckdb.DuckDBPyConnection",
    settings: Settings,
    source_table: str = "ga4_events",
    models_dir: Path = GA4_MODELS_DIR,
) -> list[str]:
    """Build every model into a DuckDB connection. Used by the offline tests."""
    built = []
    for model in discover_models(models_dir):
        sql = to_duckdb(render(model, "duckdb", settings, source_table=source_table))
        con.execute(f"CREATE OR REPLACE TABLE {model.name} AS {sql}")
        built.append(model.name)
    return built
