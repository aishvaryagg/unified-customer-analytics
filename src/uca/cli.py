"""Command line for building the project's BigQuery tables.

  uca compile [ga4|mind|all]     render models to BigQuery SQL files for review
  uca build [ga4|mind|all]       build models as BigQuery tables
  uca mind-download              download MIND into MIND_DATA_DIR
  uca mind-load                  load the downloaded MIND files into BigQuery
  uca sf-load                    load the sf_* tables into Salesforce
  uca build-embeddings           embed MIND article text for semantic search
  uca ask "question"             answer a plain-English question from the data
"""

from __future__ import annotations

import argparse
from pathlib import Path

from uca.config import Settings
from uca.sql import GROUPS


def _groups(value: str) -> tuple[str, ...]:
    return GROUPS if value == "all" else (value,)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="uca", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    group_choices = (*GROUPS, "all")

    p_compile = sub.add_parser("compile", help="Render models to BigQuery SQL files")
    p_compile.add_argument("group", nargs="?", default="all", choices=group_choices)
    p_compile.add_argument("--out", type=Path, default=Path("target/compiled"))
    p_compile.add_argument("--select", nargs="*", help="Only these models")

    p_build = sub.add_parser("build", help="Build models as BigQuery tables")
    p_build.add_argument("group", nargs="?", default="all", choices=group_choices)
    p_build.add_argument("--select", nargs="*", help="Only these models (upstream must exist)")

    sub.add_parser("mind-download", help="Download MIND train and dev splits")
    sub.add_parser("mind-load", help="Load downloaded MIND files into BigQuery")
    sub.add_parser("sf-load", help="Load the sf_* BigQuery tables into Salesforce")
    sub.add_parser("build-embeddings", help="Embed MIND article text in BigQuery")
    p_ask = sub.add_parser("ask", help="Answer a plain-English question")
    p_ask.add_argument("question")
    p_ask.add_argument("--show-sql", action="store_true", help="Print each step's SQL")
    p_ask.add_argument("--no-search", action="store_true", help="Skip semantic search")

    args = parser.parse_args(argv)
    settings = Settings.from_env()

    if args.command == "compile":
        from uca.runners import compile_bigquery

        for path in compile_bigquery(settings, args.out, _groups(args.group), args.select):
            print(path)
    elif args.command == "build":
        from uca.runners import build_bigquery

        build_bigquery(settings, _groups(args.group), args.select)
    elif args.command == "mind-download":
        from uca.mind import download

        download(settings)
    elif args.command == "mind-load":
        from uca.mind import load_bigquery

        load_bigquery(settings)
    elif args.command == "sf-load":
        from uca.salesforce import load_from_bigquery

        results = load_from_bigquery(settings)
        if any(r.errors for r in results):
            raise SystemExit(1)
    elif args.command == "build-embeddings":
        from uca.ai.semantic import build_embeddings

        build_embeddings(settings)
    elif args.command == "ask":
        _ask(settings, args)


def _ask(settings: Settings, args) -> None:
    from uca.ai.assistant import ask
    from uca.ai.executors import BigQueryExecutor
    from uca.ai.llm import ClaudeLLM
    from uca.ai.semantic import BigQuerySemanticSearch

    executor = BigQueryExecutor(settings)
    searcher = None if args.no_search else BigQuerySemanticSearch(settings, client=executor.client)
    result = ask(args.question, ClaudeLLM(settings.llm_model), executor, settings, searcher)

    print(result.answer.answer)
    for caveat in result.answer.caveats:
        print(f"  - {caveat}")
    print()
    for step in result.steps:
        status = "ok" if step.ok else f"failed: {step.error}"
        tries = f", {step.attempts} attempt(s)" if step.step.kind.endswith("_sql") else ""
        print(f"[{step.step.kind}] {step.step.question} ({status}{tries})")
        if args.show_sql:
            for sql in step.sql:
                print(f"    {sql}")


if __name__ == "__main__":
    main()
