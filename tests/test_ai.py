"""AI question layer, offline: a scripted stand-in for Claude, DuckDB for the warehouse."""

from types import SimpleNamespace

import pytest

from uca.ai import catalog
from uca.ai.assistant import Answer, RoutePlan, Step, ask, reader_profile
from uca.ai.executors import BigQueryExecutor, DuckDBExecutor
from uca.ai.guard import UnsafeSQLError, validate
from uca.ai.llm import ClaudeLLM, LLMError, LLMRefusal
from uca.ai.semantic import BigQuerySemanticSearch
from uca.ai.sql_agent import SQLDraft, answer_with_sql
from uca.config import Settings


class ScriptedLLM:
    """Returns queued responses per output type and records every call."""

    def __init__(self, **queues):
        self.queues = {name: list(items) for name, items in queues.items()}
        self.calls = []

    def structured(self, system, user, output_type, effort="high"):
        self.calls.append(SimpleNamespace(system=system, user=user, type=output_type, effort=effort))
        queue = self.queues[output_type.__name__]
        return queue.pop(0)


def draft(sql, explanation="ok"):
    return SQLDraft(sql=sql, explanation=explanation)


# --- guard ----------------------------------------------------------------------------

ALLOWED = {"mart_attribution", "mart_channel_performance"}


@pytest.mark.parametrize("sql", [
    "SELECT * FROM mart_attribution",
    "WITH t AS (SELECT channel_group FROM mart_attribution) SELECT * FROM t",
    "SELECT a.channel_group FROM mart_attribution a JOIN mart_channel_performance c USING (channel_group)",
    "SELECT * FROM mart_attribution, UNNEST([1, 2]) AS n",
])
def test_guard_accepts_read_only_queries_on_allowed_tables(sql):
    validate(sql, ALLOWED, 10)


@pytest.mark.parametrize("sql, message", [
    ("DELETE FROM mart_attribution WHERE TRUE", "Only SELECT"),
    ("DROP TABLE mart_attribution", "Only SELECT"),
    ("SELECT 1; SELECT 2", "exactly one"),
    ("SELECT * FROM stg_ga4__events", "not available"),
    ("SELECT * FROM mart_mind__topic_drift", "not available"),
    ("SELECT * FROM other_project.ds.mart_attribution", "bare table name"),
    ("SELECT * FROM region.INFORMATION_SCHEMA.TABLES", "bare table name"),
    ("SELECT * FROM EXTERNAL_QUERY('conn', 'SELECT 1')", "not allowed"),
    ("SELEC nonsense FROM", "could not be parsed"),
])
def test_guard_rejects_with_actionable_messages(sql, message):
    with pytest.raises(UnsafeSQLError, match=message):
        validate(sql, ALLOWED, 10)


def test_guard_caps_rows():
    assert validate("SELECT * FROM mart_attribution", ALLOWED, 25).args["limit"].expression.name == "25"
    assert validate("SELECT * FROM mart_attribution LIMIT 5", ALLOWED, 25).args["limit"].expression.name == "5"
    assert validate("SELECT * FROM mart_attribution LIMIT 999", ALLOWED, 25).args["limit"].expression.name == "25"
    union = validate("SELECT 1 AS x FROM mart_attribution UNION ALL SELECT 2 FROM mart_attribution", ALLOWED, 3)
    assert union.sql(dialect="bigquery").endswith("LIMIT 3")


# --- catalog --------------------------------------------------------------------------

def test_catalog_exposes_only_marts_and_data_quality_tables():
    ga4 = catalog.allowed_tables("ga4")
    assert "mart_attribution" in ga4 and "dq_ga4__placeholder_share" in ga4
    assert not any(t.startswith(("stg_", "int_", "sf_")) for t in ga4)
    mind = catalog.allowed_tables("mind")
    assert "mart_mind__topic_drift" in mind and not ga4 & mind


def test_catalog_descriptions_come_from_model_headers(warehouse):
    [attribution] = [t for t in catalog.tables("ga4") if t.name == "mart_attribution"]
    assert attribution.description.startswith("Revenue credited to each channel")
    text = catalog.describe("ga4", DuckDBExecutor(warehouse))
    assert "## mart_attribution" in text and "attribution_model VARCHAR" in text
    assert "NO revenue" in catalog.summary()


# --- SQL agent ------------------------------------------------------------------------

def test_sql_agent_fixes_a_failing_query(warehouse):
    llm = ScriptedLLM(SQLDraft=[
        draft("SELECT channel, SUM(revenue_usd) AS revenue FROM mart_attribution GROUP BY 1"),
        draft("SELECT channel_group, revenue_usd FROM mart_attribution "
              "WHERE attribution_model = 'last_touch' ORDER BY revenue_usd DESC"),
    ])
    result = answer_with_sql("Revenue by channel, last touch?", "ga4", llm, DuckDBExecutor(warehouse))
    assert result.ok and len(result.attempts) == 2
    assert result.rows[0] == {"channel_group": "Organic Search", "revenue_usd": 55.0}
    assert "LIMIT 200" in result.sql
    retry_prompt = llm.calls[1].user
    assert "previous attempts failed" in retry_prompt and "channel" in retry_prompt
    assert "Query failed" in retry_prompt
    assert "## mart_attribution" in llm.calls[0].system


def test_sql_agent_feeds_back_guard_rejections(warehouse):
    llm = ScriptedLLM(SQLDraft=[
        draft("SELECT COUNT(*) AS n FROM stg_ga4__purchases"),
        draft("SELECT SUM(transactions) AS n FROM mart_channel_performance"),
    ])
    result = answer_with_sql("How many orders?", "ga4", llm, DuckDBExecutor(warehouse))
    assert result.ok and result.rows == [{"n": 6}]
    assert result.attempts[0].error.startswith("Rejected before running")
    assert "stg_ga4__purchases" in llm.calls[1].user


def test_sql_agent_gives_up_after_max_attempts(warehouse):
    llm = ScriptedLLM(SQLDraft=[draft("SELECT nope FROM mart_attribution")] * 3)
    result = answer_with_sql("?", "ga4", llm, DuckDBExecutor(warehouse), max_attempts=3)
    assert not result.ok and len(result.attempts) == 3
    assert "No working query after 3 attempts" in result.error


def test_sql_agent_stops_when_model_says_not_answerable(warehouse):
    llm = ScriptedLLM(SQLDraft=[draft("", "MIND has no revenue data.")])
    result = answer_with_sql("MIND revenue?", "mind", llm, DuckDBExecutor(warehouse))
    assert not result.ok and result.attempts == [] and "no revenue" in result.error


# --- assistant ------------------------------------------------------------------------

class FakeSearch:
    def __init__(self):
        self.queries = []

    def search(self, query, top_k=10):
        self.queries.append((query, top_k))
        return [{"news_id": "N3", "title": "Stocks rally on rate hopes", "category": "finance",
                 "distance": 0.12, "times_shown": 3, "clicks": 3}]


def test_compound_question_runs_each_step_and_combines_results(warehouse, settings):
    plan = RoutePlan(supported=True, reason="Needs a number and a topic search.", steps=[
        Step(kind="ga4_sql", question="Which channel has the most last-touch revenue?", reader_id=""),
        Step(kind="content_search", question="articles about stock markets", reader_id=""),
    ])
    llm = ScriptedLLM(
        RoutePlan=[plan],
        SQLDraft=[draft("SELECT channel_group, revenue_usd FROM mart_attribution "
                        "WHERE attribution_model = 'last_touch' ORDER BY revenue_usd DESC LIMIT 1")],
        Answer=[Answer(answer="Organic Search leads with $55.", caveats=["GA4 is a sample."])],
    )
    search = FakeSearch()
    result = ask("Top channel, and what market news is read?", llm, DuckDBExecutor(warehouse), settings, search)
    assert [s.ok for s in result.steps] == [True, True]
    assert result.steps[0].rows == [{"channel_group": "Organic Search", "revenue_usd": 55.0}]
    assert search.queries == [("articles about stock markets", 10)]
    final_prompt = llm.calls[-1].user
    assert "Organic Search" in final_prompt and "Stocks rally on rate hopes" in final_prompt
    assert [c.type.__name__ for c in llm.calls] == ["RoutePlan", "SQLDraft", "Answer"]
    assert result.answer.answer.startswith("Organic Search")


def test_unsupported_question_runs_nothing(warehouse, settings):
    llm = ScriptedLLM(RoutePlan=[RoutePlan(
        supported=False, reason="MIND has no revenue data.", steps=[])])
    result = ask("How much revenue did sports articles make?", llm, DuckDBExecutor(warehouse), settings)
    assert result.steps == [] and len(llm.calls) == 1
    assert "MIND has no revenue data" in result.answer.answer


def test_content_search_without_embeddings_fails_gracefully(warehouse, settings):
    llm = ScriptedLLM(
        RoutePlan=[RoutePlan(supported=True, reason="search", steps=[
            Step(kind="content_search", question="holiday gifts", reader_id="")])],
        Answer=[Answer(answer="Search is not set up.", caveats=[])],
    )
    result = ask("What do gift guides cover?", llm, DuckDBExecutor(warehouse), settings, searcher=None)
    assert not result.steps[0].ok and "build-embeddings" in result.steps[0].error
    assert "build-embeddings" in llm.calls[-1].user


def test_reader_profile(warehouse):
    result = reader_profile("U1", DuckDBExecutor(warehouse))
    assert result.ok
    sections = {r["section"] for r in result.rows}
    assert sections == {"engagement", "status", "topic_drift", "recent_reads"}
    status = [r for r in result.rows if r["section"] == "status"][0]
    assert status["engagement_status"] == "Passive"
    drifting = [r for r in result.rows if r["section"] == "topic_drift" and r["direction"] == "Drifting away"]
    assert [r["category"] for r in drifting] == ["sports"]


def test_reader_profile_rejects_bad_or_unknown_ids(warehouse):
    assert "not a MIND reader id" in reader_profile("U1' OR '1'='1", DuckDBExecutor(warehouse)).error
    assert "No reader U999" in reader_profile("U999", DuckDBExecutor(warehouse)).error


# --- Claude wrapper -------------------------------------------------------------------

class FakeMessages:
    def __init__(self, response):
        self.response, self.kwargs = response, None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def fake_client(response):
    messages = FakeMessages(response)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def test_claude_request_uses_structured_output_fallbacks_and_caching():
    parsed = Answer(answer="hi", caveats=[])
    client, messages = fake_client(SimpleNamespace(stop_reason="end_turn", parsed_output=parsed))
    assert ClaudeLLM(client=client).structured("system text", "question", Answer, effort="medium") is parsed
    kw = messages.kwargs
    assert kw["model"] == "claude-opus-5"
    assert kw["output_format"] is Answer and kw["output_config"] == {"effort": "medium"}
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert kw["system"] == [{"type": "text", "text": "system text", "cache_control": {"type": "ephemeral"}}]
    assert kw["messages"] == [{"role": "user", "content": "question"}]


def test_claude_refusal_and_truncation_raise():
    client, _ = fake_client(SimpleNamespace(
        stop_reason="refusal", stop_details=SimpleNamespace(explanation="declined"), parsed_output=None))
    with pytest.raises(LLMRefusal, match="declined"):
        ClaudeLLM(client=client).structured("s", "u", Answer)
    client, _ = fake_client(SimpleNamespace(stop_reason="max_tokens", parsed_output=None))
    with pytest.raises(LLMError, match="cut off"):
        ClaudeLLM(client=client).structured("s", "u", Answer)


# --- BigQuery pieces (no network) -----------------------------------------------------

BQ = Settings(gcp_project="demo-project", bq_dataset="marketing_analytics")


def test_bigquery_executor_qualifies_tables_but_not_ctes():
    executor = BigQueryExecutor(BQ, client=object())
    query = validate("WITH t AS (SELECT * FROM mart_attribution) SELECT * FROM t", ALLOWED, 10)
    sql = executor.sql(query)
    assert "`demo-project`.`marketing_analytics`.`mart_attribution`" in sql
    assert "FROM `t`" in sql


def test_semantic_search_passes_the_question_as_a_parameter():
    captured = {}

    class Client:
        def query(self, sql, job_config):
            captured.update(sql=sql, params=job_config.query_parameters)
            return SimpleNamespace(result=lambda: [])

    BigQuerySemanticSearch(BQ, client=Client()).search("holiday gift ideas'; DROP", top_k=5)
    assert "top_k => 5" in captured["sql"]
    assert "@query" in captured["sql"] and "holiday gift" not in captured["sql"]
    assert "`demo-project.marketing_analytics.mind_text_embedding`" in captured["sql"]
    assert captured["params"][0].value == "holiday gift ideas'; DROP"
