"""Export the rpt_* reporting tables as CSV files (for Tableau Public / Desktop extracts)."""

from __future__ import annotations

import csv
import datetime as dt
import decimal
from pathlib import Path
from typing import Callable, Iterable

from uca.config import Settings
from uca.sql import discover_models

REPORT_TABLES = tuple(m.name for m in discover_models("reporting"))


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    return v


def write_csv(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        if not rows:
            return path
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({k: _cell(v) for k, v in row.items()} for row in rows)
    return path


def export(read_table: Callable[[str], Iterable[dict]], out_dir: Path) -> list[Path]:
    return [write_csv(list(read_table(table)), Path(out_dir) / f"{table}.csv") for table in REPORT_TABLES]


def export_bigquery(settings: Settings, out_dir: Path) -> list[Path]:
    from uca.runners import bigquery_client
    from uca.sql import table_ref

    client = bigquery_client(settings)

    def read_table(table: str) -> list[dict]:
        rows = client.query(f"SELECT * FROM {table_ref(table, 'bigquery', settings)}").result()
        return [dict(row.items()) for row in rows]

    return export(read_table, out_dir)
