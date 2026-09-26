"""The governed catalog: which tables the AI may query, and how they are described.

Only mart and data-quality tables are exposed; staging tables stay hidden. Each table's
description is the comment block at the top of its SQL model, so the definitions the
model sees are the same ones documented in the code. Columns are read from the warehouse.
"""

from __future__ import annotations

from dataclasses import dataclass

from uca.sql import discover_models

DATASETS = ("ga4", "mind")

DATASET_NOTES = {
    "ga4": (
        "Google Analytics 4 obfuscated e-commerce sample (Google Merchandise Store, "
        "2020-11-01 to 2021-01-31). Revenue is in USD. Some values are obfuscated "
        "('<Other>', '(data deleted)', shown as '(obfuscated)' / channel 'Obfuscated')."
    ),
    "mind": (
        "Microsoft MIND news-reading data (about one week in November 2019). Engagement "
        "only: impressions and clicks. MIND has NO revenue or monetary data. MIND readers "
        "are different people from GA4 shoppers and must never be joined to GA4 tables."
    ),
}


@dataclass(frozen=True)
class CatalogTable:
    name: str
    dataset: str
    description: str


def _header(template: str) -> str:
    lines = []
    for line in template.splitlines():
        if not line.startswith("--"):
            break
        lines.append(line[2:].strip())
    return "\n".join(lines).strip()


def tables(dataset: str) -> list[CatalogTable]:
    if dataset not in DATASETS:
        raise ValueError(f"Unknown dataset {dataset!r}")
    return [
        CatalogTable(m.name, dataset, _header(m.template))
        for m in discover_models(dataset)
        if m.name.startswith(("mart_", "dq_"))
    ]


def allowed_tables(dataset: str) -> set[str]:
    return {t.name for t in tables(dataset)}


def describe(dataset: str, executor) -> str:
    """Catalog text for the SQL prompt: notes, then each table's definition and columns."""
    parts = [f"Dataset: {dataset}. {DATASET_NOTES[dataset]}"]
    for t in tables(dataset):
        cols = ", ".join(f"{name} {type_}" for name, type_ in executor.columns(t.name))
        parts.append(f"## {t.name}\n{t.description}\nColumns: {cols}")
    return "\n\n".join(parts)


def summary() -> str:
    """One line per table, for the router."""
    lines = []
    for dataset in DATASETS:
        lines.append(f"{dataset}: {DATASET_NOTES[dataset]}")
        for t in tables(dataset):
            first = t.description.splitlines()[0] if t.description else ""
            lines.append(f"  - {t.name}: {first}")
    return "\n".join(lines)
