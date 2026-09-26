"""Rendering and macro checks that do not need data."""

import duckdb
import pytest
import sqlglot

from uca.config import Settings
from uca.sql import GROUPS, channel_group, clean_label, discover_models, render, to_duckdb

BQ = Settings(gcp_project="demo-project", bq_dataset="marketing_analytics")


def test_models_are_discovered_in_build_order():
    names = [m.name for m in discover_models()]
    assert names[:4] == ["stg_ga4__events", "stg_ga4__purchases", "stg_ga4__items", "int_ga4__sessions"]
    assert len(names) == len(set(names))


ALL_MODELS = [m for group in GROUPS for m in discover_models(group)]


def test_model_names_are_unique_across_groups():
    names = [m.name for m in ALL_MODELS]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("model", ALL_MODELS, ids=lambda m: m.name)
def test_every_model_renders_valid_bigquery_sql(model):
    sql = render(model, "bigquery", BQ)
    assert "{{" not in sql and "{%" not in sql
    parsed = sqlglot.parse(sql, read="bigquery")
    assert len(parsed) == 1
    if "ref(" in model.template:
        assert "`demo-project.marketing_analytics." in sql


def test_source_uses_wildcard_table_suffix_in_bigquery():
    events = discover_models()[0]
    sql = render(events, "bigquery", BQ)
    assert "`bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`" in sql
    assert "_TABLE_SUFFIX BETWEEN '20201101' AND '20210131'" in sql


def test_bigquery_render_requires_project():
    with pytest.raises(ValueError, match="GCP_PROJECT"):
        render(discover_models()[1], "bigquery", Settings())


@pytest.mark.parametrize(
    "source, medium, expected",
    [
        ("(direct)", "(none)", "Direct"),
        ("google", "organic", "Organic Search"),
        ("google", "cpc", "Paid Search"),
        ("facebook", "referral", "Social"),
        ("m.facebook.com", "social", "Social"),
        ("newsletter", "email", "Email"),
        ("partner", "affiliate", "Affiliates"),
        ("gdn", "display", "Display"),
        ("shop.googlemerchandisestore.com", "referral", "Referral"),
        ("<Other>", "<Other>", "Obfuscated"),
        ("google", "(data deleted)", "Obfuscated"),
        ("something", "weird", "Unassigned"),
    ],
)
def test_channel_group(source, medium, expected):
    sql = to_duckdb(f"SELECT {channel_group(repr(source), repr(medium))}")
    assert duckdb.sql(sql).fetchone()[0] == expected


@pytest.mark.parametrize(
    "value, expected",
    [("<Other>", "(obfuscated)"), ("(data deleted)", "(obfuscated)"), ("(not set)", "(not set)"),
     ("", "(not set)"), (None, "(not set)"), ("winter_sale", "winter_sale")],
)
def test_clean_label(value, expected):
    literal = "NULL" if value is None else repr(value)
    sql = to_duckdb(f"SELECT {clean_label(f'CAST({literal} AS STRING)')}")
    assert duckdb.sql(sql).fetchone()[0] == expected
