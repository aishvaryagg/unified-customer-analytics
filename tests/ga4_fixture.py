"""A tiny, hand-built GA4 events table with known answers.

Four users, Nov 2020 - Jan 2021 (data ends 2021-01-31):

u1  first touch google/organic
    s1 2020-11-02  google/organic   full funnel, buys t1: A $10 + B $20 = $30
    s2 2020-11-10  newsletter/email buys t2: A $10 + C $35 = $45    (Expansion)
    s3 2020-11-17  (direct)/(none)  buys t3: B $20 = $20            (Contraction)
    s4 2021-01-25  no source params  page view only                   -> active, not churned
u2  first touch (direct)/(none)
    s1 2020-11-03  google/cpc winter_sale  views B, adds B to cart
    s2 2020-11-04  google/cpc winter_sale  buys t4: A $10 + B $20 = $30, logged TWICE
    only one purchasing week -> Insufficient history; churned
u3  first touch <Other>/<Other>
    s1 2020-12-01  <Other>/<Other>  page view only; churned
u4  first touch google/organic
    s1 2020-11-05  google/organic   buys t5: A $10 + B $15 = $25
    s2 2020-11-12  facebook/social  buys t6: C $25 = $25            (Flat); churned

Products: A = "Tee" (Apparel), B = "Tote" (Bags), C = "Mug" (Drinkware).
"""

from __future__ import annotations

from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE ga4_events (
  event_date VARCHAR,
  event_timestamp BIGINT,
  event_name VARCHAR,
  event_params STRUCT(
    key VARCHAR,
    value STRUCT(string_value VARCHAR, int_value BIGINT, float_value DOUBLE, double_value DOUBLE)
  )[],
  user_id VARCHAR,
  user_pseudo_id VARCHAR,
  device STRUCT(category VARCHAR, operating_system VARCHAR),
  geo STRUCT(country VARCHAR),
  traffic_source STRUCT(name VARCHAR, medium VARCHAR, source VARCHAR),
  ecommerce STRUCT(transaction_id VARCHAR, purchase_revenue_in_usd DOUBLE, total_item_quantity BIGINT),
  items STRUCT(
    item_id VARCHAR, item_name VARCHAR, item_category VARCHAR,
    price_in_usd DOUBLE, quantity BIGINT, item_revenue_in_usd DOUBLE
  )[]
)
"""

PRODUCTS = {
    "A": ("Tee", "Apparel"),
    "B": ("Tote", "Bags"),
    "C": ("Mug", "Drinkware"),
}

FIRST_TOUCH = {
    "u1": ("google", "organic", "(organic)"),
    "u2": ("(direct)", "(none)", "(direct)"),
    "u3": ("<Other>", "<Other>", "<Other>"),
    "u4": ("google", "organic", "(organic)"),
}


def _param(key, value):
    if isinstance(value, int):
        v = {"string_value": None, "int_value": value, "float_value": None, "double_value": None}
    else:
        v = {"string_value": value, "int_value": None, "float_value": None, "double_value": None}
    return {"key": key, "value": v}


def _item(code, price):
    name, category = PRODUCTS[code]
    return {
        "item_id": code, "item_name": name, "item_category": category,
        "price_in_usd": float(price), "quantity": 1, "item_revenue_in_usd": float(price),
    }


def _event(user, when, name, session_id, session_number, source=None, medium=None,
           campaign=None, device="desktop", items=None, transaction=None):
    ts = datetime.strptime(when, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    params = [_param("ga_session_id", session_id), _param("ga_session_number", session_number)]
    for key, value in (("source", source), ("medium", medium), ("campaign", campaign)):
        if value is not None:
            params.append(_param(key, value))
    items = items or []
    ecommerce = None
    if transaction:
        ecommerce = {
            "transaction_id": transaction,
            "purchase_revenue_in_usd": sum(i["price_in_usd"] for i in items),
            "total_item_quantity": len(items),
        }
    ft_source, ft_medium, ft_name = FIRST_TOUCH[user]
    return (
        ts.strftime("%Y%m%d"),
        int(ts.timestamp() * 1_000_000),
        name,
        params,
        None,
        user,
        {"category": device, "operating_system": "Web"},
        {"country": "United States"},
        {"name": ft_name, "medium": ft_medium, "source": ft_source},
        ecommerce,
        items,
    )


def _session(user, day, session_id, number, steps, **kwargs):
    """A session as a list of (minute, event_name, extra kwargs) steps."""
    rows = []
    for minute, name, extra in steps:
        rows.append(_event(user, f"{day} 10:{minute:02d}", name, session_id, number,
                           **{**kwargs, **extra}))
    return rows


def rows():
    r = []
    t1 = [_item("A", 10), _item("B", 20)]
    r += _session("u1", "2020-11-02", 1001, 1, [
        (0, "session_start", {}),
        (1, "page_view", {}),
        (2, "view_item", {"items": [_item("A", 10)]}),
        (3, "add_to_cart", {"items": [_item("A", 10)]}),
        (4, "begin_checkout", {"items": t1}),
        (5, "purchase", {"items": t1, "transaction": "t1"}),
    ], source="google", medium="organic", campaign="(organic)")
    t2 = [_item("A", 10), _item("C", 35)]
    r += _session("u1", "2020-11-10", 1002, 2, [
        (0, "session_start", {}),
        (1, "purchase", {"items": t2, "transaction": "t2"}),
    ], source="newsletter", medium="email", campaign="nov_newsletter")
    r += _session("u1", "2020-11-17", 1003, 3, [
        (0, "session_start", {}),
        (1, "purchase", {"items": [_item("B", 20)], "transaction": "t3"}),
    ], source="(direct)", medium="(none)")
    r += _session("u1", "2021-01-25", 1004, 4, [
        (0, "page_view", {}),
    ])

    r += _session("u2", "2020-11-03", 2001, 1, [
        (0, "session_start", {}),
        (1, "view_item", {"items": [_item("B", 20)]}),
        (2, "add_to_cart", {"items": [_item("B", 20)]}),
    ], source="google", medium="cpc", campaign="winter_sale", device="mobile")
    t4 = [_item("A", 10), _item("B", 20)]
    r += _session("u2", "2020-11-04", 2002, 2, [
        (0, "session_start", {}),
        (1, "purchase", {"items": t4, "transaction": "t4"}),
        (2, "purchase", {"items": t4, "transaction": "t4"}),  # duplicate hit
    ], source="google", medium="cpc", campaign="winter_sale", device="mobile")

    r += _session("u3", "2020-12-01", 3001, 1, [
        (0, "session_start", {}),
        (1, "page_view", {}),
    ], source="<Other>", medium="<Other>", campaign="<Other>")

    t5 = [_item("A", 10), _item("B", 15)]
    r += _session("u4", "2020-11-05", 4001, 1, [
        (0, "session_start", {}),
        (1, "purchase", {"items": t5, "transaction": "t5"}),
    ], source="google", medium="organic", campaign="(organic)")
    r += _session("u4", "2020-11-12", 4002, 2, [
        (0, "session_start", {}),
        (1, "purchase", {"items": [_item("C", 25)], "transaction": "t6"}),
    ], source="facebook", medium="social", campaign="(referral)")
    return r


def load(con) -> None:
    con.execute(SCHEMA)
    con.executemany("INSERT INTO ga4_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows())
