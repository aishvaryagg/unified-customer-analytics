"""Answer a plain-English question: route it, run each step, then write the answer.

Step kinds:
  ga4_sql         commerce / marketing numbers from the GA4 tables (generated SQL)
  mind_sql        content engagement numbers from the MIND tables (generated SQL)
  content_search  what articles are about, found by meaning (semantic search)
  reader_profile  one MIND reader's engagement, drift and recent reading (fixed queries)

A compound question ("which channel brings the most revenue, and what topics are
disengaging readers reading?") becomes several steps whose results are combined in one
answer. GA4 and MIND results are reported side by side, never joined.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

from uca.ai import catalog
from uca.ai.guard import validate
from uca.ai.sql_agent import SQLResult, answer_with_sql

StepKind = Literal["ga4_sql", "mind_sql", "content_search", "reader_profile"]

ROUTER_SYSTEM = """You plan how to answer a marketing analyst's question from two separate datasets.

{catalog}

Break the question into 1 to 4 steps. Each step is self-contained and uses one dataset:
- ga4_sql: numbers about the online store (sessions, funnel, channels, campaigns,
  attribution, revenue, customers, products, churn, retention).
- mind_sql: numbers about news readers (impressions, clicks, click-through, categories,
  engagement trends, topic drift, disengagement).
- content_search: questions about what articles are about or which articles match a theme,
  answered by searching article titles and abstracts by meaning.
- reader_profile: summarize one MIND reader's engagement. Put their id (like U12345) in
  reader_id. For every other kind, reader_id is an empty string.

Mark the question unsupported (supported = false, no steps) when it needs data these
tables do not have, for example revenue or money from MIND, linking GA4 shoppers to MIND
readers as the same people, or data outside these tables. Give the reason in plain words.
When it is supported, reason briefly explains the plan."""

ANSWER_SYSTEM = """You answer a marketing analyst's question using only the results provided.

- Lead with the direct answer, then the supporting numbers. Keep it short and plain.
- Use only numbers that appear in the results; do not estimate or invent values.
- GA4 (online store) and MIND (news readers) are different businesses and people. Report
  them side by side; never imply they are the same customers. MIND has no revenue.
- If a step failed or returned nothing, say what could not be answered.
- Add caveats that matter for the numbers: GA4 is an obfuscated sample from Nov 2020 to
  Jan 2021; MIND covers about one week in Nov 2019 and measures engagement only."""


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: StepKind
    question: str
    reader_id: str


class RoutePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported: bool
    reason: str
    steps: list[Step]


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    caveats: list[str]


@dataclass
class StepResult:
    step: Step
    ok: bool
    rows: list[dict] = field(default_factory=list)
    sql: list[str] = field(default_factory=list)
    attempts: int = 0
    error: str | None = None


@dataclass
class AskResult:
    question: str
    plan: RoutePlan
    steps: list[StepResult]
    answer: Answer


READER_ID = re.compile(r"^U\d{1,12}$")

READER_QUERIES = {
    "engagement": "SELECT * FROM mart_mind__user_engagement_trend WHERE user_id = '{uid}'",
    "status": "SELECT * FROM mart_mind__user_disengagement WHERE user_id = '{uid}'",
    "topic_drift": (
        "SELECT category, past_share, current_share, share_change, direction, drift_score "
        "FROM mart_mind__topic_drift WHERE user_id = '{uid}' ORDER BY share_change"
    ),
    "recent_reads": (
        "SELECT read_rank, category, subcategory, title, abstract, source "
        "FROM mart_mind__pre_disengagement_reads WHERE user_id = '{uid}' ORDER BY read_rank"
    ),
}


def reader_profile(reader_id: str, executor, max_rows: int = 200) -> StepResult:
    step = Step(kind="reader_profile", question=f"Profile of reader {reader_id}", reader_id=reader_id)
    if not READER_ID.match(reader_id):
        return StepResult(step, ok=False, error=f"{reader_id!r} is not a MIND reader id (like U12345).")
    allowed = catalog.allowed_tables("mind")
    rows, sqls = [], []
    for section, template in READER_QUERIES.items():
        query = validate(template.format(uid=reader_id), allowed, max_rows)
        sqls.append(query.sql(dialect="bigquery"))
        rows += [{"section": section, **r} for r in executor.run(query)]
    if not any(r["section"] == "engagement" for r in rows):
        return StepResult(step, ok=False, sql=sqls, error=f"No reader {reader_id} in the MIND data.")
    return StepResult(step, ok=True, rows=rows, sql=sqls, attempts=1)


def _from_sql(step: Step, result: SQLResult) -> StepResult:
    return StepResult(
        step, ok=result.ok, rows=result.rows, sql=[a.sql for a in result.attempts],
        attempts=len(result.attempts), error=result.error,
    )


def run_step(step: Step, llm, executor, searcher, settings) -> StepResult:
    if step.kind in ("ga4_sql", "mind_sql"):
        dataset = step.kind.split("_")[0]
        return _from_sql(step, answer_with_sql(
            step.question, dataset, llm, executor,
            max_attempts=settings.ai_max_sql_attempts, max_rows=settings.ai_max_rows,
        ))
    if step.kind == "reader_profile":
        result = reader_profile(step.reader_id, executor, settings.ai_max_rows)
        result.step = step
        return result
    if searcher is None:
        return StepResult(step, ok=False, error=(
            "Semantic search is not set up. Run `uca build-embeddings` (see docs/ai.md)."))
    try:
        return StepResult(step, ok=True, rows=searcher.search(step.question, top_k=10), attempts=1)
    except Exception as e:
        return StepResult(step, ok=False, error=f"Semantic search failed: {str(e).splitlines()[0][:300]}")


def _results_for_prompt(results: list[StepResult], row_limit: int = 50) -> str:
    payload = []
    for r in results:
        item = {"kind": r.step.kind, "question": r.step.question, "ok": r.ok}
        if r.ok:
            item["rows"] = r.rows[:row_limit]
            item["row_count"] = len(r.rows)
        else:
            item["error"] = r.error
        payload.append(item)
    return json.dumps(payload, indent=2, default=str)


def ask(question: str, llm, executor, settings, searcher=None) -> AskResult:
    plan = llm.structured(
        ROUTER_SYSTEM.format(catalog=catalog.summary()), f"Question: {question}", RoutePlan, effort="medium")
    if not plan.supported or not plan.steps:
        answer = Answer(answer=f"This can't be answered from the project's data: {plan.reason}", caveats=[])
        return AskResult(question, plan, [], answer)
    results = [run_step(step, llm, executor, searcher, settings) for step in plan.steps]
    answer = llm.structured(
        ANSWER_SYSTEM,
        f"Question: {question}\n\nResults:\n{_results_for_prompt(results)}",
        Answer,
        effort="medium",
    )
    return AskResult(question, plan, results, answer)
