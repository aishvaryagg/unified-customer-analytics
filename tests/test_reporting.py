"""Reporting tables, CSV export, the Tableau palette file and the Sheets summary script."""

import csv
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest

from conftest import query
from uca.reporting import REPORT_TABLES, export

ROOT = Path(__file__).resolve().parents[1]


def by(rows, *keys):
    return {tuple(r[k] for k in keys) if len(keys) > 1 else r[keys[0]]: r for r in rows}


def test_kpis(reporting):
    k = by(query(reporting, "SELECT * FROM rpt_kpis"), "source", "metric")
    assert k[("GA4", "sessions")]["value"] == 9
    assert k[("GA4", "revenue_usd")]["value"] == 175
    assert k[("GA4", "conversion_rate")]["value"] == pytest.approx(6 / 9)
    assert k[("GA4", "avg_order_value_usd")]["value"] == pytest.approx(175 / 6)
    assert k[("GA4", "churned_share")]["value"] == 0.75
    assert k[("MIND", "clicks")]["value"] == 10
    assert k[("MIND", "click_through_rate")]["value"] == pytest.approx(10 / 18)
    assert k[("MIND", "disengaged_share")]["value"] == 0.25
    assert k[("MIND", "drifting_readers")]["value"] == 1
    assert {r["unit"] for r in k.values()} == {"count", "usd", "ratio"}
    # MIND never reports money.
    assert not any(src == "MIND" and r["unit"] == "usd" for (src, _), r in k.items())


def test_trend_distribution_uses_common_labels(reporting):
    t = by(query(reporting, "SELECT * FROM rpt_trend_distribution"), "source", "trend")
    assert t[("GA4", "Contraction")]["people"] == 1 and t[("GA4", "Flat")]["people"] == 1
    mind = t[("MIND", "Contraction")]
    assert mind["people"] == 2 and mind["trend_label"] == "Engagement contraction"
    assert mind["share"] == 0.5
    assert {trend for _, trend in t} <= {"Expansion", "Contraction", "Flat", "Insufficient history"}


def test_retention_status(reporting):
    r = by(query(reporting, "SELECT * FROM rpt_retention_status"), "source", "population", "status")
    assert r[("GA4", "Shoppers", "Churned")]["people"] == 3
    assert r[("GA4", "Customers", "Lapsed")]["share"] == 1.0
    assert {s for src, _, s in r if src == "MIND"} == {"Engaged", "Passive", "Disengaged", "Insufficient history"}


def test_weekly_channels_fold_small_channels_into_other(reporting):
    rows = query(reporting, "SELECT * FROM rpt_ga4_weekly_channels")
    channels = {r["channel"] for r in rows}
    assert channels == {"Organic Search", "Email", "Paid Search", "Social", "Direct", "Other"}
    assert sum(r["revenue_usd"] for r in rows) == 175
    w = by(rows, "week_start", "channel")
    assert w[(date(2020, 11, 2), "Organic Search")]["sessions"] == 2
    assert w[(date(2020, 11, 30), "Other")]["sessions"] == 1  # the obfuscated session


def test_mind_daily_categories(reporting):
    rows = query(reporting, "SELECT * FROM rpt_mind_daily_categories")
    assert sum(r["times_shown"] for r in rows) == 18 and sum(r["clicks"] for r in rows) == 10
    d = by(rows, "activity_date", "category")
    assert d[(date(2019, 11, 10), "finance")]["clicks"] == 3
    assert len({r["category"] for r in rows}) <= 7


def test_csv_export(reporting, tmp_path):
    paths = export(lambda t: query(reporting, f"SELECT * FROM {t}"), tmp_path)
    assert [p.stem for p in paths] == list(REPORT_TABLES)
    with open(tmp_path / "rpt_ga4_weekly_channels.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows and "2020-11-02" in {r["week_start"] for r in rows}


def test_tableau_palette_file_is_valid_xml():
    root = ET.parse(ROOT / "reporting" / "tableau" / "Preferences.tps").getroot()
    palettes = {p.get("name"): [c.text for c in p] for p in root.iter("color-palette")}
    assert len(palettes["UCA Categorical"]) == 6
    assert all(c.startswith("#") and len(c) == 7 for colors in palettes.values() for c in colors)


# --- Apps Script summary, run in Node ------------------------------------------------

NODE = shutil.which("node")
RUNNER = """
const fs = require('fs'); const vm = require('vm');
const sandbox = { module: { exports: {} } };
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const lib = sandbox.module.exports;
const out = {
  summary: lib.buildSummary(input.kpis, input.trends, input.retention),
  records: lib.toRecords(input.fields, input.raw).records,
  usd: lib.fmtUsd(1234567.891, 2),
};
process.stdout.write(JSON.stringify(out));
"""


def run_script(payload):
    script = ROOT / "reporting" / "sheets" / "Code.gs"
    done = subprocess.run([NODE, "-e", RUNNER, str(script)], input=json.dumps(payload),
                          capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_sheets_summary_reads_the_reporting_tables(reporting):
    payload = {
        "kpis": query(reporting, "SELECT * FROM rpt_kpis"),
        "trends": query(reporting, "SELECT * FROM rpt_trend_distribution"),
        "retention": query(reporting, "SELECT * FROM rpt_retention_status"),
        "fields": [{"name": "channel", "type": "STRING"}, {"name": "sessions", "type": "INTEGER"},
                   {"name": "rate", "type": "FLOAT"}, {"name": "flag", "type": "BOOLEAN"}],
        "raw": [{"f": [{"v": "Email"}, {"v": "12"}, {"v": "0.5"}, {"v": "true"}]},
                {"f": [{"v": None}, {"v": "3"}, {"v": None}, {"v": "false"}]}],
    }
    out = run_script(payload)
    text = "\n".join(out["summary"])
    assert "9 sessions from 4 shoppers produced 6 orders and $175 in revenue" in text
    assert "conversion rate 66.7%" in text and "average order $29.17" in text
    assert "Of GA4 customers with at least two active periods, 0 spent more week over week, " \
           "1 spent less and 1 held flat; 1 had too little history to judge." in text
    assert "4 readers saw 9 impressions and clicked 10 articles (click-through rate 55.6%)" in text
    assert "25.0% of readers had disengaged" in text and "1 reader was drifting" in text
    assert out["summary"][-1].startswith("GA4 and MIND are different businesses")
    assert out["records"] == [
        {"channel": "Email", "sessions": 12, "rate": 0.5, "flag": True},
        {"channel": None, "sessions": 3, "rate": None, "flag": False},
    ]
    assert out["usd"] == "$1,234,567.89"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_sheets_summary_is_empty_without_data():
    assert run_script({"kpis": [], "trends": [], "retention": [], "fields": [], "raw": []})["summary"] == []
