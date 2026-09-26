"""Command line for building the project's BigQuery tables.

  uca compile [ga4|mind|all]     render models to BigQuery SQL files for review
  uca build [ga4|mind|all]       build models as BigQuery tables
  uca mind-download              download MIND into MIND_DATA_DIR
  uca mind-load                  load the downloaded MIND files into BigQuery
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


if __name__ == "__main__":
    main()
