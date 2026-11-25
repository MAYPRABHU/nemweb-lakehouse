"""Command line interface: `nemweb run | backfill | check | summary | sql`."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

import polars as pl

from nemweb import gold
from nemweb.config import REPORTS
from nemweb.fetch import HttpSource, LocalSource
from nemweb.pipeline import RunResult, run_backfill, run_current
from nemweb.quality import run_checks
from nemweb.warehouse import Warehouse


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nemweb", description=__doc__)
    p.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("NEMWEB_DATA_DIR", "data")),
        help="where the DuckDB file and raw zips live (default: ./data)",
    )
    p.add_argument("--no-raw", action="store_true", help="don't keep raw zips (bronze)")
    p.add_argument(
        "--source-dir",
        type=Path,
        help="read zips from a local folder (Current/<folder>, Archive/<folder>) instead of NEMWeb",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    report_help = f"reports to load (default: all). Options: {', '.join(REPORTS)}"

    run = sub.add_parser("run", help="load the latest files from NEMWeb /Reports/Current")
    run.add_argument("--report", nargs="+", choices=list(REPORTS), help=report_help)
    run.add_argument(
        "--limit",
        type=int,
        default=12,
        help="latest N files per report (default 12 = last hour; 0 = all)",
    )

    bf = sub.add_parser("backfill", help="load daily files from NEMWeb /Reports/Archive")
    bf.add_argument("--start", type=date.fromisoformat, required=True, help="YYYY-MM-DD")
    bf.add_argument("--end", type=date.fromisoformat, help="YYYY-MM-DD (default: same as start)")
    bf.add_argument("--report", nargs="+", choices=list(REPORTS), help=report_help)

    sub.add_parser("check", help="run data quality checks (exit code 1 if any fail)")

    sm = sub.add_parser("summary", help="show daily price summary from the gold layer")
    sm.add_argument("--days", type=int, default=7)

    sq = sub.add_parser("sql", help="run any SQL against the warehouse")
    sq.add_argument("query")
    return p


def _print_result(res: RunResult) -> int:
    print(
        f"\nfiles: {res.files_found} found, {res.files_loaded} loaded, "
        f"{res.files_skipped} already done, {len(res.failures)} failed"
    )
    for table, n in sorted(res.rows_by_table.items()):
        print(f"  {table:<22} {n:>10,} rows upserted")
    for name, err in res.failures:
        print(f"  FAILED {name}: {err}")
    return 1 if res.failures else 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    pl.Config.set_tbl_rows(50)
    pl.Config.set_tbl_cols(20)

    wh = Warehouse(args.data_dir / "nem.duckdb")
    bronze = None if args.no_raw else args.data_dir / "bronze"
    try:
        if args.command in ("run", "backfill"):
            reports = [REPORTS[r] for r in (args.report or REPORTS)]
            source = LocalSource(args.source_dir) if args.source_dir else HttpSource()
            if args.command == "run":
                res = run_current(wh, source, reports, args.limit, bronze)
            else:
                res = run_backfill(wh, source, reports, args.start, args.end or args.start, bronze)
            built = gold.build_views(wh)
            code = _print_result(res)
            if built:
                print(f"gold views: {', '.join(built)}")
            return code

        if args.command == "check":
            results = run_checks(wh)
            if not results:
                print("nothing to check yet — run `nemweb run` first")
                return 0
            for r in results:
                print(f"[{'PASS' if r.passed else 'FAIL'}] {r.name}: {r.detail}")
            return 0 if all(r.passed for r in results) else 1

        if args.command == "summary":
            if "daily_region_price" not in gold.build_views(wh):
                print("no price data yet — run `nemweb run` first")
                return 0
            print(
                wh.query(
                    f"SELECT * FROM gold.daily_region_price "
                    f"WHERE trading_date >= (SELECT max(trading_date) FROM gold.daily_region_price)"
                    f" - INTERVAL {args.days - 1} DAY ORDER BY trading_date, region"
                )
            )
            return 0

        if args.command == "sql":
            gold.build_views(wh)
            print(wh.query(args.query))
            return 0
    finally:
        wh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
