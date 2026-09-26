"""The MIND TSV reader and CLI wiring, without network or Google Cloud."""

import pytest

import mind_fixture
from uca.mind import BEHAVIOR_COLUMNS, NEWS_COLUMNS, raw_rows, read_tsv


def test_read_tsv_keeps_quotes_and_pads_missing_fields(tmp_path):
    path = tmp_path / "news.tsv"
    path.write_text('N1\tnews\tnewsus\tSay "hello"\t\thttps://x\t[{"Label": "A"}]\n', encoding="utf-8")
    [row] = list(read_tsv(path, NEWS_COLUMNS, "train"))
    assert row["split"] == "train"
    assert row["title"] == 'Say "hello"'
    assert row["abstract"] == ""
    assert row["title_entities"] == '[{"Label": "A"}]'
    assert row["abstract_entities"] == ""  # missing trailing field


def test_read_tsv_rejects_extra_fields(tmp_path):
    path = tmp_path / "behaviors.tsv"
    path.write_text("1\tU1\t11/9/2019 9:00:00 AM\t\tN1-1\textra\n")
    with pytest.raises(ValueError, match="6 fields, expected 5"):
        list(read_tsv(path, BEHAVIOR_COLUMNS, "train"))


def test_raw_rows_reads_both_splits(tmp_path):
    mind_fixture.write(tmp_path)
    rows = list(raw_rows(tmp_path, "mind_raw_behaviors"))
    assert [r["split"] for r in rows].count("dev") == 1
    assert len(rows) == 9


def test_raw_rows_explains_missing_files(tmp_path):
    with pytest.raises(FileNotFoundError, match="uca mind-download"):
        list(raw_rows(tmp_path, "mind_raw_news"))


def test_cli_compile_writes_both_groups(tmp_path, monkeypatch):
    from uca.cli import main

    monkeypatch.setenv("GCP_PROJECT", "demo-project")
    main(["compile", "--out", str(tmp_path)])
    assert (tmp_path / "ga4" / "int_ga4__sessions.sql").exists()
    mind_sql = (tmp_path / "mind" / "stg_mind__news.sql").read_text()
    assert "`demo-project.marketing_analytics.mind_raw_news`" in mind_sql
