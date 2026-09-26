"""Validate generated SQL before it runs.

The model writes BigQuery SQL against bare table names. A query is accepted only if it:
- is a single read-only SELECT (CTEs and set operations allowed),
- reads only tables on the allow-list for its dataset (no staging tables, no other datasets,
  no qualified names, no ML./EXTERNAL_QUERY-style functions),
- returns at most ``max_rows`` rows (a LIMIT is added or lowered).
The error messages are written to be fed back to the model so it can fix its query.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp


class UnsafeSQLError(ValueError):
    """The SQL is not allowed to run. The message explains why."""


FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
    exp.Command, exp.TruncateTable,
)
FORBIDDEN_FUNCTION_PREFIXES = ("ML.", "EXTERNAL_QUERY", "VECTOR_SEARCH", "AI.", "KEYS.", "SESSION_USER")


def validate(sql: str, allowed_tables: set[str], max_rows: int) -> exp.Expression:
    """Parse and check a query. Returns the (possibly LIMIT-adjusted) expression."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="bigquery") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQLError(f"SQL could not be parsed: {e}") from e
    if len(statements) != 1:
        raise UnsafeSQLError(f"Write exactly one SELECT statement (got {len(statements)}).")
    root = statements[0]
    if not isinstance(root, (exp.Select, exp.SetOperation)):
        raise UnsafeSQLError("Only SELECT queries are allowed.")
    for node in root.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeSQLError(f"{type(node).__name__} statements are not allowed; read-only SELECT only.")
        if isinstance(node, (exp.Anonymous, exp.Func)):
            name = node.sql(dialect="bigquery").split("(")[0].upper()
            if name.startswith(FORBIDDEN_FUNCTION_PREFIXES):
                raise UnsafeSQLError(f"Function {name} is not allowed.")

    cte_names = {cte.alias_or_name for cte in root.find_all(exp.CTE)}
    for table in root.find_all(exp.Table):
        if table.name in cte_names and not table.db:
            continue
        if table.db or table.catalog:
            raise UnsafeSQLError(
                f"Use the bare table name, not {table.sql(dialect='bigquery')}. "
                "The dataset is added automatically."
            )
        if table.name not in allowed_tables:
            raise UnsafeSQLError(
                f"Table {table.name!r} is not available. Use only: {', '.join(sorted(allowed_tables))}."
            )
    return _cap_rows(root, max_rows)


def _cap_rows(root: exp.Expression, max_rows: int) -> exp.Expression:
    if isinstance(root, exp.SetOperation):
        return exp.select("*").from_(root.subquery("capped")).limit(max_rows)
    limit = root.args.get("limit")
    if limit is None:
        return root.limit(max_rows)
    try:
        current = int(limit.expression.name)
    except (AttributeError, ValueError):
        return root.limit(max_rows)
    return root.limit(min(current, max_rows))
