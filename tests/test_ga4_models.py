"""Each GA4 model checked against answers worked out by hand from ga4_fixture.py."""

from datetime import date

import pytest

from conftest import query


def by(rows, *keys):
    return {tuple(r[k] for k in keys) if len(keys) > 1 else r[keys[0]]: r for r in rows}


def test_events_get_session_keys(ga4):
    rows = query(ga4, "SELECT DISTINCT session_key FROM stg_ga4__events ORDER BY 1")
    assert [r["session_key"] for r in rows] == [
        "u1.1001", "u1.1002", "u1.1003", "u1.1004",
        "u2.2001", "u2.2002", "u3.3001", "u4.4001", "u4.4002",
    ]


def test_duplicate_purchase_is_counted_once(ga4):
    rows = query(ga4, "SELECT transaction_key, revenue_usd FROM stg_ga4__purchases ORDER BY 1")
    assert [(r["transaction_key"], r["revenue_usd"]) for r in rows] == [
        ("t1", 30), ("t2", 45), ("t3", 20), ("t4", 30), ("t5", 25), ("t6", 25),
    ]
    items = query(ga4, "SELECT COUNT(*) AS n FROM stg_ga4__items WHERE transaction_key = 't4'")
    assert items[0]["n"] == 2


def test_sessions_attribution_and_funnel_flags(ga4):
    s = by(query(ga4, "SELECT * FROM int_ga4__sessions"), "session_key")
    assert len(s) == 9
    assert s["u1.1001"]["channel_group"] == "Organic Search"
    assert s["u1.1002"]["channel_group"] == "Email"
    assert s["u1.1003"]["channel_group"] == "Direct"
    assert s["u1.1004"]["channel_group"] == "Direct"  # no source params -> direct
    assert s["u2.2001"]["channel_group"] == "Paid Search"
    assert s["u2.2001"]["campaign"] == "winter_sale"
    assert s["u3.3001"]["channel_group"] == "Obfuscated"
    assert s["u3.3001"]["campaign"] == "(obfuscated)"
    assert s["u4.4002"]["channel_group"] == "Social"

    first = s["u1.1001"]
    assert first["is_new_user"] and first["reached_view_item"] and first["reached_add_to_cart"]
    assert first["reached_checkout"] and first["reached_purchase"]
    assert first["revenue_usd"] == 30
    assert s["u2.2002"]["transactions"] == 1 and s["u2.2002"]["revenue_usd"] == 30
    assert not s["u2.2001"]["reached_purchase"]


def test_funnel_totals(ga4):
    t = query(ga4, """
        SELECT SUM(sessions) s, SUM(view_item_sessions) v, SUM(add_to_cart_sessions) c,
               SUM(checkout_sessions) k, SUM(purchase_sessions) p
        FROM mart_funnel_daily""")[0]
    assert (t["s"], t["v"], t["c"], t["k"], t["p"]) == (9, 2, 2, 1, 6)
    paid = query(ga4, """
        SELECT * FROM mart_funnel_daily
        WHERE session_date = DATE '2020-11-03' AND channel_group = 'Paid Search'""")[0]
    assert paid["device_category"] == "mobile"
    assert paid["view_to_cart_rate"] == 1.0
    assert paid["cart_to_checkout_rate"] == 0.0
    assert paid["checkout_to_purchase_rate"] is None  # no checkouts: undefined, not zero


def test_channel_performance(ga4):
    c = by(query(ga4, "SELECT * FROM mart_channel_performance"), "channel_group", "campaign")
    paid = c[("Paid Search", "winter_sale")]
    assert paid["sessions"] == 2 and paid["users"] == 1 and paid["transactions"] == 1
    assert paid["revenue_usd"] == 30 and paid["conversion_rate"] == 0.5
    organic = c[("Organic Search", "(organic)")]
    assert organic["sessions"] == 2 and organic["revenue_usd"] == 55
    assert organic["avg_order_value_usd"] == 27.5
    total = query(ga4, "SELECT SUM(revenue_usd) r FROM mart_channel_performance")[0]["r"]
    assert total == 175


def test_attribution_models(ga4):
    a = by(query(ga4, "SELECT * FROM mart_attribution"), "attribution_model", "channel_group")
    for model in ("first_touch", "last_touch", "linear"):
        total = sum(r["revenue_usd"] for (m, _), r in a.items() if m == model)
        conversions = sum(r["conversions"] for (m, _), r in a.items() if m == model)
        assert total == pytest.approx(175), model
        assert conversions == pytest.approx(6), model

    assert a[("first_touch", "Organic Search")]["revenue_usd"] == 145
    assert a[("first_touch", "Direct")]["revenue_usd"] == 30

    assert a[("last_touch", "Organic Search")]["revenue_usd"] == 55
    assert a[("last_touch", "Email")]["revenue_usd"] == 45
    assert a[("last_touch", "Paid Search")]["revenue_usd"] == 30

    assert a[("linear", "Organic Search")]["revenue_usd"] == pytest.approx(30 + 22.5 + 20 / 3 + 25 + 12.5)
    assert a[("linear", "Email")]["revenue_usd"] == pytest.approx(22.5 + 20 / 3)
    assert a[("linear", "Direct")]["revenue_usd"] == pytest.approx(20 / 3)
    assert a[("linear", "Social")]["revenue_usd"] == pytest.approx(12.5)


def test_weekly_revenue_trend_labels(ga4):
    w = by(query(ga4, "SELECT * FROM mart_user_weekly_revenue"), "user_pseudo_id", "week_start")
    assert w[("u1", date(2020, 11, 2))]["trend"] == "Baseline"
    assert w[("u1", date(2020, 11, 9))]["trend"] == "Expansion"
    assert w[("u1", date(2020, 11, 9))]["revenue_change_pct"] == pytest.approx(0.5)
    assert w[("u1", date(2020, 11, 16))]["trend"] == "Contraction"
    assert w[("u4", date(2020, 11, 9))]["trend"] == "Flat"
    # One purchasing week (with a duplicated purchase) must not produce a trend.
    only = w[("u2", date(2020, 11, 2))]
    assert only["trend"] == "Insufficient history" and only["revenue_usd"] == 30


def test_same_week_purchases_are_summed_before_labelling(ga4, settings):
    """Two purchases in one week are one data point, never Expansion/Contraction."""
    import duckdb

    from ga4_fixture import SCHEMA, _event, _item
    from uca.runners import build_duckdb

    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute(SCHEMA)
    rows = [
        _event("u1", "2020-11-02 09:00", "purchase", 1, 1, items=[_item("A", 10)], transaction="x1"),
        _event("u1", "2020-11-02 18:00", "purchase", 2, 2, items=[_item("B", 50)], transaction="x2"),
    ]
    con.executemany("INSERT INTO ga4_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    build_duckdb(con, settings)
    out = query(con, "SELECT * FROM mart_user_weekly_revenue")
    assert len(out) == 1
    assert out[0]["revenue_usd"] == 60 and out[0]["trend"] == "Insufficient history"


def test_user_revenue_trend(ga4):
    u = by(query(ga4, "SELECT * FROM mart_user_revenue_trend"), "user_pseudo_id")
    assert set(u) == {"u1", "u2", "u4"}
    assert u["u1"]["latest_trend"] == "Contraction"
    assert u["u1"]["revenue_usd"] == 95 and u["u1"]["active_weeks"] == 3
    assert u["u1"]["first_purchase_week"] == date(2020, 11, 2)
    assert u["u4"]["latest_trend"] == "Flat"
    assert u["u2"]["latest_trend"] == "Insufficient history"


def test_product_affinity(ga4):
    p = by(query(ga4, "SELECT * FROM mart_product_affinity"), "product_a", "product_b")
    tee_tote = p[("Tee", "Tote")]
    assert tee_tote["transactions_with_both"] == 3
    assert tee_tote["support"] == pytest.approx(3 / 6)
    assert tee_tote["confidence"] == pytest.approx(3 / 4)
    assert tee_tote["lift"] == pytest.approx((3 / 4) / (4 / 6))
    assert p[("Mug", "Tee")]["confidence"] == pytest.approx(1 / 2)
    assert p[("Tee", "Mug")]["lift"] == pytest.approx((1 / 4) / (2 / 6))
    assert ("Tote", "Mug") not in p


def test_next_category(ga4):
    n = by(query(ga4, "SELECT * FROM mart_next_category"), "segment", "from_category", "to_category")
    top = n[("All customers", "Apparel", "Drinkware")]
    assert top["transitions"] == 2 and top["purchase_pairs"] == 3
    assert top["probability"] == pytest.approx(2 / 3) and top["rank_in_segment"] == 1
    assert n[("All customers", "Apparel", "Bags")]["probability"] == pytest.approx(1 / 3)
    assert n[("All customers", "Drinkware", "Bags")]["transitions"] == 1
    # Categories already in the earlier purchase are not "next" categories.
    assert ("All customers", "Bags", "Apparel") not in n
    assert n[("Organic Search", "Bags", "Drinkware")]["transitions"] == 2
    # u2 has one purchase, so the Direct-acquired segment has no pairs.
    assert not any(seg == "Direct" for seg, _, _ in n)


def test_rfm_and_churn(ga4):
    u = by(query(ga4, "SELECT * FROM mart_user_rfm_churn"), "user_pseudo_id")
    assert u["u1"]["days_since_last_seen"] == 6 and not u["u1"]["is_churned"]
    assert u["u1"]["is_lapsed_purchaser"]  # last purchase 2020-11-17
    assert u["u2"]["is_churned"] and u["u2"]["transactions"] == 1
    assert u["u3"]["is_churned"] and u["u3"]["rfm_segment"] == "Non-purchaser"
    assert u["u3"]["recency_score"] is None
    assert u["u4"]["days_since_last_seen"] == 80 and u["u4"]["is_churned"]
    assert u["u1"]["sessions"] == 4
    for user in ("u1", "u2", "u4"):
        for score in ("recency_score", "frequency_score", "monetary_score"):
            assert 1 <= u[user][score] <= 5


def test_cohort_retention(ga4):
    c = by(query(ga4, "SELECT * FROM mart_cohort_retention"), "cohort_week", "week_number")
    nov2 = date(2020, 11, 2)
    assert c[(nov2, 0)]["cohort_users"] == 3 and c[(nov2, 0)]["retention_rate"] == 1.0
    assert c[(nov2, 1)]["active_users"] == 2
    assert c[(nov2, 2)]["active_users"] == 1
    assert c[(nov2, 12)]["active_users"] == 1  # u1 returns on 2021-01-25
    assert c[(date(2020, 11, 30), 0)]["cohort_users"] == 1


def test_placeholder_share(ga4):
    d = by(query(ga4, "SELECT * FROM dq_ga4__placeholder_share"), "field")
    src = d["event_params.source"]
    assert src["obfuscated_rows"] == 2 and src["placeholder_rows"] == 2
    assert d["traffic_source.source"]["obfuscated_rows"] == 2  # u3's two events
    assert d["items.item_name"]["placeholder_rows"] == 0
