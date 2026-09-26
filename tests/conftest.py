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
