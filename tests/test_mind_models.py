"""Each MIND model checked against answers worked out by hand from mind_fixture.py."""

from datetime import date, datetime

import pytest

from conftest import query


def by(rows, *keys):
    return {tuple(r[k] for k in keys) if len(keys) > 1 else r[keys[0]]: r for r in rows}


def test_news_deduplicated_across_splits(mind):
    rows = query(mind, "SELECT news_id, abstract FROM stg_mind__news ORDER BY news_id")
    assert [r["news_id"] for r in rows] == ["N1", "N2", "N3", "N4", "N5", "N6"]
    assert by(rows, "news_id")["N5"]["abstract"] is None  # empty abstract -> NULL


def test_impressions_parse_time_and_keep_split_ids_apart(mind):
    i = by(query(mind, "SELECT * FROM stg_mind__impressions"), "impression_key")
    assert set(i) == {"train-1", "train-2", "train-3", "train-4", "train-5", "train-6",
                      "train-8", "train-9", "dev-1"}
    assert i["train-3"]["impression_ts"] == datetime(2019, 11, 14, 20, 0)
    assert i["dev-1"]["impression_ts"] == datetime(2019, 11, 15, 23, 0)
    assert i["train-1"]["impression_date"] == date(2019, 11, 9)
    assert i["train-4"]["history"] is None


def test_impression_items(mind):
    t = query(mind, "SELECT COUNT(*) n, COUNT_IF(clicked) c FROM stg_mind__impression_items")[0]
    assert (t["n"], t["c"]) == (18, 10)
    items = query(mind, """SELECT news_id, clicked FROM stg_mind__impression_items
                           WHERE impression_key = 'train-2' ORDER BY news_id""")
    assert [(r["news_id"], r["clicked"]) for r in items] == [("N3", True), ("N5", True), ("N6", False)]


def test_history_recency(mind):
    h = query(mind, "SELECT news_id, recency_rank FROM stg_mind__history WHERE user_id = 'U1' ORDER BY 2")
    assert [r["news_id"] for r in h] == ["N3", "N2", "N1"]  # newest first
    assert query(mind, "SELECT COUNT(*) n FROM stg_mind__history WHERE user_id = 'U2'")[0]["n"] == 0


def test_daily_engagement_trend(mind):
    d = by(query(mind, "SELECT * FROM mart_mind__user_daily_engagement"), "user_id", "activity_date")
    assert d[("U1", date(2019, 11, 9))]["trend"] == "Baseline"
    assert d[("U1", date(2019, 11, 10))]["trend"] == "Engagement expansion"
    assert d[("U1", date(2019, 11, 10))]["clicked_categories"] == 1
    assert d[("U1", date(2019, 11, 14))]["trend"] == "Engagement contraction"
    assert d[("U3", date(2019, 11, 15))]["clicks_change_pct"] == pytest.approx(-0.5)
    assert d[("U4", date(2019, 11, 10))]["trend"] == "Flat"
    # Two impressions on one day are one data point, not a trend.
    u2 = d[("U2", date(2019, 11, 9))]
    assert u2["impressions"] == 2 and u2["clicks"] == 2 and u2["trend"] == "Insufficient history"


def test_user_engagement_trend(mind):
    u = by(query(mind, "SELECT * FROM mart_mind__user_engagement_trend"), "user_id")
    assert u["U1"]["latest_trend"] == "Engagement contraction"
    assert u["U1"]["clicks"] == 3 and u["U1"]["articles_shown"] == 9
    assert u["U1"]["click_through_rate"] == pytest.approx(3 / 9)
    assert u["U1"]["first_active_date"] == date(2019, 11, 9)
    assert u["U2"]["latest_trend"] == "Insufficient history"
    assert u["U4"]["latest_trend"] == "Flat"


def test_category_performance(mind):
    c = by(query(mind, "SELECT * FROM mart_mind__category_performance"), "category", "subcategory")
    assert c[("finance", "markets")]["times_shown"] == 3 and c[("finance", "markets")]["clicks"] == 3
    assert c[("lifestyle", "lifestyleroyals")]["times_shown"] == 5
    assert c[("lifestyle", "lifestyleroyals")]["click_through_rate"] == pytest.approx(3 / 5)
    assert c[("lifestyle", "lifestyleroyals")]["readers_clicked"] == 2
    assert c[("sports", "football_nfl")]["history_clicks"] == 1
    assert c[("(unknown)", "(unknown)")]["times_shown"] == 1  # N99
    assert sum(r["times_shown"] for r in c.values()) == 18
    assert sum(r["history_clicks"] for r in c.values()) == 5


def test_topic_drift(mind):
    t = by(query(mind, "SELECT * FROM mart_mind__topic_drift"), "user_id", "category")
    # Only U1 has at least 3 clicks both before and during the log.
    assert {u for u, _ in t} == {"U1"}
    sports = t[("U1", "sports")]
    assert sports["past_share"] == pytest.approx(2 / 3) and sports["current_share"] == 0
    assert sports["direction"] == "Drifting away"
    assert t[("U1", "finance")]["direction"] == "Growing interest"
    assert sports["drift_score"] == pytest.approx(2 / 3)


def test_disengagement(mind):
    u = by(query(mind, "SELECT * FROM mart_mind__user_disengagement"), "user_id")
    assert u["U4"]["engagement_status"] == "Disengaged"
    assert u["U4"]["hours_since_last_impression"] == 135
    assert u["U1"]["engagement_status"] == "Passive"  # still shown articles, no clicks
    assert u["U2"]["engagement_status"] == "Insufficient history"
    assert u["U3"]["engagement_status"] == "Engaged"


def test_pre_disengagement_reads(mind):
    r = query(mind, "SELECT * FROM mart_mind__pre_disengagement_reads ORDER BY user_id, read_rank")
    assert {row["user_id"] for row in r} == {"U1", "U4"}
    u4 = [(row["news_id"], row["source"]) for row in r if row["user_id"] == "U4"]
    assert u4 == [("N3", "impression_log"), ("N6", "impression_log"), ("N6", "history")]
    u1 = [row for row in r if row["user_id"] == "U1"]
    assert len(u1) == 6
    assert [row["news_id"] for row in u1[3:]] == ["N3", "N2", "N1"]  # history, newest first
    assert u1[0]["title"] and u1[0]["engagement_status"] == "Passive"


def test_dq_summary(mind):
    d = query(mind, "SELECT * FROM dq_mind__summary")[0]
    assert d["news_articles"] == 6 and d["news_missing_abstract"] == 1
    assert d["impressions"] == 9 and d["readers"] == 4
    assert d["articles_shown"] == 18 and d["clicks"] == 10
    assert d["shown_missing_from_news"] == 1 and d["shown_without_click_label"] == 0
    assert d["impressions_without_history"] == 2
    assert d["data_end_ts"] == datetime(2019, 11, 15, 23, 0)
