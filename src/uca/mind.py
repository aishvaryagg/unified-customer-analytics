"""Download Microsoft MIND and load it into BigQuery (or DuckDB for local work).

MIND is published by Microsoft Research under the Microsoft Research License Terms for
non-commercial research use. The files are downloaded to MIND_DATA_DIR, which is
git-ignored: they must not be committed or redistributed.

Each split is a zip holding two headerless TSV files:
  news.tsv       news_id, category, subcategory, title, abstract, url,
                 title_entities, abstract_entities
  behaviors.tsv  impression_id, user_id, time, history, impressions

Both are loaded as-is (all columns STRING) into ``mind_raw_news`` and
``mind_raw_behaviors``, with a ``split`` column. Parsing happens in the SQL models.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from uca.config import Settings

if TYPE_CHECKING:
    import duckdb

SPLITS = ("train", "dev")  # the test split has no click labels, so it is not used

DOWNLOAD_URLS = {
    "small": "https://mind201910small.blob.core.windows.net/release/MINDsmall_{split}.zip",
    "large": "https://mind201910.blob.core.windows.net/release/MINDlarge_{split}.zip",
}

NEWS_COLUMNS = (
    "news_id", "category", "subcategory", "title", "abstract", "url",
    "title_entities", "abstract_entities",
)
BEHAVIOR_COLUMNS = ("impression_id", "user_id", "time", "history", "impressions")

RAW_TABLES = {
    "mind_raw_news": ("news.tsv", NEWS_COLUMNS),
    "mind_raw_behaviors": ("behaviors.tsv", BEHAVIOR_COLUMNS),
}

# Titles contain long fields; the csv module's default 128 KB limit is too small for some rows.
csv.field_size_limit(sys.maxsize)


def split_dir(data_dir: Path, split: str) -> Path:
    return Path(data_dir) / split


def download(settings: Settings, log=print) -> None:
    """Download and unzip the train and dev splits into MIND_DATA_DIR/<split>/."""
    if settings.mind_variant not in DOWNLOAD_URLS:
        raise ValueError(f"MIND_VARIANT must be one of {sorted(DOWNLOAD_URLS)}")
    for split in SPLITS:
        url = DOWNLOAD_URLS[settings.mind_variant].format(split=split)
        target = split_dir(Path(settings.mind_data_dir), split)
        if (target / "behaviors.tsv").exists():
            log(f"{split}: already present in {target}")
            continue
        target.mkdir(parents=True, exist_ok=True)
        log(f"{split}: downloading {url}")
        with urllib.request.urlopen(url) as response:
            payload = response.read()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for name in ("news.tsv", "behaviors.tsv"):
                member = next(m for m in archive.namelist() if m.endswith(name))
                (target / name).write_bytes(archive.read(member))
        log(f"{split}: extracted to {target}")


def read_tsv(path: Path, columns: tuple[str, ...], split: str) -> Iterator[dict]:
    """Rows of a headerless MIND TSV as dicts, with ``split`` added.

    Quotes are not special in MIND files, and missing trailing fields become ''.
    """
    with open(path, newline="", encoding="utf-8") as f:
        for line_no, fields in enumerate(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE), 1):
            if not fields:
                continue
            if len(fields) > len(columns):
                raise ValueError(f"{path}:{line_no}: {len(fields)} fields, expected {len(columns)}")
            fields += [""] * (len(columns) - len(fields))
            yield {"split": split, **dict(zip(columns, fields))}


def raw_rows(data_dir: Path, table: str) -> Iterator[dict]:
    filename, columns = RAW_TABLES[table]
    found = False
    for split in SPLITS:
        path = split_dir(data_dir, split) / filename
        if path.exists():
            found = True
            yield from read_tsv(path, columns, split)
    if not found:
        raise FileNotFoundError(
            f"No {filename} under {data_dir}/<split>/. Run `uca mind-download`, or download "
            "MIND from https://msnews.github.io/ and unzip each split into that folder."
        )


def load_bigquery(settings: Settings, log=print) -> None:
    """Replace mind_raw_news and mind_raw_behaviors in BigQuery with the local files."""
    from google.cloud import bigquery

    from uca.runners import bigquery_client

    client = bigquery_client(settings)
    data_dir = Path(settings.mind_data_dir)
    for table, (_, columns) in RAW_TABLES.items():
        schema = [bigquery.SchemaField(c, "STRING") for c in ("split", *columns)]
        job_config = bigquery.LoadJobConfig(
            schema=schema,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        with tempfile.TemporaryFile("w+b") as tmp:
            rows = 0
            for row in raw_rows(data_dir, table):
                tmp.write(json.dumps(row, ensure_ascii=False).encode("utf-8") + b"\n")
                rows += 1
            tmp.seek(0)
            destination = f"{settings.gcp_project}.{settings.bq_dataset}.{table}"
            client.load_table_from_file(tmp, destination, job_config=job_config).result()
        log(f"loaded {rows:,} rows into {destination}")


def load_duckdb(con: "duckdb.DuckDBPyConnection", data_dir: Path) -> None:
    """Create mind_raw_news and mind_raw_behaviors in DuckDB from the local files."""
    for table, (_, columns) in RAW_TABLES.items():
        all_columns = ("split", *columns)
        con.execute(
            f"CREATE OR REPLACE TABLE {table} ({', '.join(f'{c} VARCHAR' for c in all_columns)})"
        )
        placeholders = ", ".join("?" for _ in all_columns)
        rows = [tuple(r[c] for c in all_columns) for r in raw_rows(Path(data_dir), table)]
        if rows:
            con.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
