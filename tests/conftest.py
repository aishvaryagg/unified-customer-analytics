import duckdb
import pytest

from ga4_fixture import load
from uca.config import Settings
from uca.runners import build_duckdb


@pytest.fixture(scope="session")
def settings():
    return Settings(churn_days=30, trend_threshold=0.10)


@pytest.fixture(scope="session")
def ga4(settings):
    """DuckDB connection with the fixture loaded and every GA4 model built."""
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    load(con)
    build_duckdb(con, settings)
    yield con
    con.close()


def query(con, sql):
    """Rows as dicts."""
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


@pytest.fixture(scope="session")
def mind(settings, tmp_path_factory):
    """DuckDB connection with the MIND sample loaded from TSV files and every model built."""
    import mind_fixture
    from uca.mind import load_duckdb

    data_dir = mind_fixture.write(tmp_path_factory.mktemp("mind"))
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    load_duckdb(con, data_dir)
    build_duckdb(con, settings, group="mind")
    yield con
    con.close()


@pytest.fixture(scope="session")
def sf():
    """GA4 fixture plus three extra visitors, with the GA4 and Salesforce models built.

    u5  adds to cart, never buys          -> Lead, Highest_Funnel_Stage 'Add to cart'
    u6  starts checkout, never buys       -> Lead, 'Checkout'
    u7  only views a page                 -> neither
    Samples are capped at 2 contacts and 1 lead to exercise the sampling.
    """
    import ga4_fixture
    from ga4_fixture import _item, _session

    ga4_fixture.FIRST_TOUCH.update({
        "u5": ("google", "cpc", "winter_sale"),
        "u6": ("newsletter", "email", "nov_newsletter"),
        "u7": ("(direct)", "(none)", "(direct)"),
    })
    extra = []
    extra += _session("u5", "2020-12-10", 5001, 1, [
        (0, "view_item", {"items": [_item("A", 10)]}),
        (1, "add_to_cart", {"items": [_item("A", 10)]}),
    ], source="google", medium="cpc", campaign="winter_sale")
    extra += _session("u6", "2021-01-20", 6001, 1, [
        (0, "view_item", {"items": [_item("C", 25)]}),
        (1, "add_to_cart", {"items": [_item("C", 25)]}),
        (2, "begin_checkout", {"items": [_item("C", 25)]}),
    ], source="newsletter", medium="email", campaign="nov_newsletter")
    extra += _session("u7", "2021-01-05", 7001, 1, [(0, "page_view", {})])

    settings = Settings(sf_max_contacts=2, sf_max_leads=1)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    load(con)
    con.executemany("INSERT INTO ga4_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", extra)
    build_duckdb(con, settings)
    build_duckdb(con, settings, group="salesforce")
    yield con
    con.close()


@pytest.fixture(scope="session")
def sf_full():
    """Plain GA4 fixture with the Salesforce models built and no sampling cap."""
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    load(con)
    settings = Settings()
    build_duckdb(con, settings)
    build_duckdb(con, settings, group="salesforce")
    yield con
    con.close()


@pytest.fixture(scope="session")
def warehouse(settings, tmp_path_factory):
    """One DuckDB connection with both the GA4 and the MIND models built (like BigQuery)."""
    import mind_fixture
    from uca.mind import load_duckdb

    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    load(con)
    build_duckdb(con, settings)
    load_duckdb(con, mind_fixture.write(tmp_path_factory.mktemp("mind-ai")))
    build_duckdb(con, settings, group="mind")
    yield con
    con.close()
