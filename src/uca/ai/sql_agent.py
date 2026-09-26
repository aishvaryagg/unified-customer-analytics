"""Generate SQL for a question, check it, run it, and fix it if it fails.

Each attempt's SQL and error are shown to the model on the next attempt, so it can
correct unknown columns, disallowed tables, or BigQuery errors itself. Up to
``max_attempts`` attempts are made.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from uca.ai import catalog
from uca.ai.guard import UnsafeSQLError, validate

SQL_SYSTEM = """You write BigQuery Standard SQL that answers a marketing analyst's question.

Rules:
- Write exactly one read-only SELECT (CTEs are fine).
- Use only the tables listed below, by their bare name (no project or dataset prefix).
- Use the columns exactly as listed. The table descriptions define every metric; follow them.
- Keep results small and readable: aggregate, order meaningfully, and return only the columns
  the question needs. At most {max_rows} rows are returned.
- Never join GA4 tables with MIND tables and never compute money from MIND data.
- If the question cannot be answered from these tables, return an empty sql string and say
  why in the explanation.

{catalog}"""


class SQLDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str
    explanation: str


@dataclass
class Attempt:
    sql: str
    error: str | None = None


@dataclass
class SQLResult:
    question: str
    dataset: str
    ok: bool
    rows: list[dict] = field(default_factory=list)
    sql: str = ""
    explanation: str = ""
    attempts: list[Attempt] = field(default_factory=list)
    error: str | None = None


def _user_prompt(question: str, attempts: list[Attempt]) -> str:
    text = f"Question: {question}"
    if attempts:
        history = [{"sql": a.sql, "error": a.error} for a in attempts]
        text += (
            "\n\nYour previous attempts failed. Fix the problem and try again.\n"
            + json.dumps(history, indent=2)
        )
    return text


def answer_with_sql(
    question: str, dataset: str, llm, executor, max_attempts: int = 3, max_rows: int = 200
) -> SQLResult:
    system = SQL_SYSTEM.format(max_rows=max_rows, catalog=catalog.describe(dataset, executor))
    allowed = catalog.allowed_tables(dataset)
    result = SQLResult(question=question, dataset=dataset, ok=False)
    for _ in range(max_attempts):
        draft = llm.structured(system, _user_prompt(question, result.attempts), SQLDraft, effort="high")
        result.explanation = draft.explanation
        if not draft.sql.strip():
            result.error = f"Not answerable from the {dataset} tables: {draft.explanation}"
            return result
        attempt = Attempt(sql=draft.sql)
        result.attempts.append(attempt)
        try:
            query = validate(draft.sql, allowed, max_rows)
            rows = executor.run(query)
        except UnsafeSQLError as e:
            attempt.error = f"Rejected before running: {e}"
            continue
        except Exception as e:  # database errors are reported back to the model
            attempt.error = f"Query failed: {str(e).splitlines()[0][:500]}"
            continue
        result.ok, result.rows, result.sql = True, rows, query.sql(dialect="bigquery")
        return result
    result.error = f"No working query after {max_attempts} attempts: {result.attempts[-1].error}"
    return result
