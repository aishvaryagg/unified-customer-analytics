"""Command line: ``uca compile`` and ``uca build``."""

from __future__ import annotations

import argparse
from pathlib import Path

from uca.config import Settings
from uca.runners import build_bigquery, compile_bigquery


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="uca", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_compile = sub.add_parser("compile", help="Render the GA4 models to BigQuery SQL files")
    p_compile.add_argument("--out", type=Path, default=Path("target/compiled/ga4"))
    p_compile.add_argument("--select", nargs="*", help="Only these models")

    p_build = sub.add_parser("build", help="Build the GA4 models as BigQuery tables")
    p_build.add_argument("--select", nargs="*", help="Only these models (upstream must exist)")

    args = parser.parse_args(argv)
    settings = Settings.from_env()

    if args.command == "compile":
        for path in compile_bigquery(settings, args.out, args.select):
            print(path)
    elif args.command == "build":
        build_bigquery(settings, args.select)


if __name__ == "__main__":
    main()
