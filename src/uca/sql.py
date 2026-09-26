"""Discover, render and translate the SQL models.

Models are written in BigQuery SQL with a few Jinja helpers:

- ``{{ ref('model_name') }}``   another model's output table
- ``{{ source_events }}``       the GA4 events table (wildcard in BigQuery)
- ``{{ table_suffix }}``        column used for the date filter on the source
- ``{{ event_param(key, type) }}``, ``{{ is_known(expr) }}``, ``{{ week_start(expr) }}``,
  ``{{ clean_label(expr) }}``, ``{{ channel_group(source, medium) }}``
- ``{{ params.<name> }}``       values from Settings

The same model renders for BigQuery (production) or DuckDB (offline tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import jinja2
import sqlglot

from uca.config import Settings

Target = Literal["bigquery", "duckdb"]

REPO_ROOT = Path(__file__).resolve().parents[2]
GA4_MODELS_DIR = REPO_ROOT / "sql" / "ga4"

# Values GA4 uses when a field is missing or hidden. '<Other>' and '(data deleted)'
# come from Google's obfuscation of the public sample.
PLACEHOLDERS = ("", "(not set)", "<Other>", "(data deleted)")
OBFUSCATED = ("<Other>", "(data deleted)")


@dataclass(frozen=True)
class Model:
    name: str
    path: Path

    @property
    def template(self) -> str:
        return self.path.read_text()


def discover_models(models_dir: Path = GA4_MODELS_DIR) -> list[Model]:
    """Models in build order. Files are named ``NN_model_name.sql``."""
    models = []
    for path in sorted(models_dir.glob("*.sql")):
        prefix, _, name = path.stem.partition("_")
        if not prefix.isdigit() or not name:
            raise ValueError(f"Model file must be named NN_name.sql: {path.name}")
        models.append(Model(name=name, path=path))
    return models


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join("'" + v.replace("'", "\\'") + "'" for v in values)


def event_param(key: str, value_type: str = "string_value") -> str:
    """Scalar subquery reading one key from GA4's ``event_params`` array."""
    return (
        f"(SELECT ep.value.{value_type} FROM UNNEST(event_params) AS ep "
        f"WHERE ep.key = '{key}')"
    )


def is_known(expr: str) -> str:
    """True when a value is present and not a GA4 placeholder."""
    return f"({expr} IS NOT NULL AND {expr} NOT IN ({_sql_list(PLACEHOLDERS)}))"


def week_start(expr: str) -> str:
    """Monday of the date's week, as a DATE (DuckDB's DATE_TRUNC returns a timestamp)."""
    return f"CAST(DATE_TRUNC({expr}, WEEK(MONDAY)) AS DATE)"


def clean_label(expr: str) -> str:
    """Normalize placeholders so obfuscated values stay visible, not silently merged."""
    return (
        f"(CASE WHEN {expr} IN ({_sql_list(OBFUSCATED)}) THEN '(obfuscated)' "
        f"WHEN {expr} IS NULL OR {expr} IN ('', '(not set)') THEN '(not set)' "
        f"ELSE {expr} END)"
    )


def channel_group(source: str, medium: str) -> str:
    """Simplified version of GA4's default channel grouping."""
    s, m = f"LOWER({source})", f"LOWER({medium})"
    obf = _sql_list(tuple(v.lower() for v in OBFUSCATED))
    return f"""(CASE
      WHEN {s} IN ({obf}) OR {m} IN ({obf}) THEN 'Obfuscated'
      WHEN {s} = '(direct)' AND ({m} IN ('(none)', '(not set)') OR {m} IS NULL) THEN 'Direct'
      WHEN {m} = 'organic' THEN 'Organic Search'
      WHEN {m} IN ('cpc', 'ppc', 'paidsearch') THEN 'Paid Search'
      WHEN REGEXP_CONTAINS({m}, r'social')
        OR {s} IN ('facebook', 'instagram', 'twitter', 't.co', 'linkedin', 'youtube') THEN 'Social'
      WHEN {m} = 'email' THEN 'Email'
      WHEN {m} = 'affiliate' THEN 'Affiliates'
      WHEN {m} IN ('display', 'cpm', 'banner') THEN 'Display'
      WHEN {m} = 'referral' THEN 'Referral'
      ELSE 'Unassigned'
    END)"""


def table_ref(name: str, target: Target, settings: Settings) -> str:
    if target == "bigquery":
        if not settings.gcp_project:
            raise ValueError("GCP_PROJECT must be set to render models for BigQuery")
        return f"`{settings.gcp_project}.{settings.bq_dataset}.{name}`"
    return name


def render(
    model: Model,
    target: Target,
    settings: Settings,
    source_table: str | None = None,
) -> str:
    """Render a model's SELECT in BigQuery SQL for the given target's table names."""
    if target == "bigquery":
        source_events = f"`{source_table or settings.ga4_source_table}`"
        table_suffix = "_TABLE_SUFFIX"
    else:
        source_events = source_table or "ga4_events"
        table_suffix = "event_date"
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
    template = env.from_string(model.template)
    return template.render(
        ref=lambda name: table_ref(name, target, settings),
        source_events=source_events,
        table_suffix=table_suffix,
        params=settings,
        event_param=event_param,
        is_known=is_known,
        clean_label=clean_label,
        week_start=week_start,
        channel_group=channel_group,
    )


def to_duckdb(bigquery_sql: str) -> str:
    """Translate rendered BigQuery SQL to DuckDB SQL for local testing."""
    statements = sqlglot.transpile(
        bigquery_sql, read="bigquery", write="duckdb", unsupported_level=sqlglot.ErrorLevel.RAISE
    )
    if len(statements) != 1:
        raise ValueError(f"Expected one statement, got {len(statements)}")
    return statements[0]
