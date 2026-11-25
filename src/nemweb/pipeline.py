"""Bronze -> silver ingestion. Incremental: files already in the manifest are skipped."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import polars as pl

from nemweb.config import TABLE_KEYS, Report
from nemweb.fetch import file_date, file_name, iter_csvs
from nemweb.parse import parse_aemo_csv
from nemweb.warehouse import Warehouse

log = logging.getLogger("nemweb")


@dataclass
class RunResult:
    files_found: int = 0
    files_loaded: int = 0
    files_skipped: int = 0
    rows_by_table: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    failures: list[tuple[str, str]] = field(default_factory=list)

    def merge(self, other: RunResult) -> None:
        self.files_found += other.files_found
        self.files_loaded += other.files_loaded
        self.files_skipped += other.files_skipped
        for t, n in other.rows_by_table.items():
            self.rows_by_table[t] += n
        self.failures.extend(other.failures)


def parse_zip(blob: bytes, tables: tuple[str, ...]) -> dict[str, pl.DataFrame]:
    """All wanted tables from every CSV inside a (possibly nested) zip."""
    parts: dict[str, list[pl.DataFrame]] = defaultdict(list)
    for _, text in iter_csvs(blob):
        for table, df in parse_aemo_csv(text, wanted=set(tables)).items():
            parts[table].append(df)
    return {
        t: dfs[0] if len(dfs) == 1 else pl.concat(dfs, how="diagonal_relaxed")
        for t, dfs in parts.items()
    }


def ingest_files(
    wh: Warehouse, source, report: Report, urls: list[str], bronze_dir: Path | None
) -> RunResult:
    result = RunResult(files_found=len(urls))
    done = wh.processed(report.name)
    todo = [u for u in urls if file_name(u) not in done]
    result.files_skipped = len(urls) - len(todo)
    log.info("%s: %d file(s) found, %d new", report.name, len(urls), len(todo))

    for url in todo:
        name = file_name(url)
        try:
            blob = source.get(url)
            if bronze_dir is not None:
                target = bronze_dir / report.name / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blob)
            frames = parse_zip(blob, report.tables)
            counts = wh.load_file(name, report.name, frames, TABLE_KEYS)
        except Exception as exc:  # keep going; report failures at the end
            log.error("FAILED %s: %s", name, exc)
            result.failures.append((name, str(exc)))
            continue
        result.files_loaded += 1
        for t, n in counts.items():
            result.rows_by_table[t] += n
        log.info("loaded %s %s", name, dict(counts))
    return result


def _safe_list(lister, report: Report, result: RunResult) -> list[str]:
    try:
        return lister(report)
    except Exception as exc:
        log.error("could not list %s: %s", report.name, exc)
        result.failures.append((f"<listing {report.name}>", str(exc)))
        return []


def run_current(
    wh: Warehouse, source, reports: list[Report], limit: int, bronze_dir: Path | None
) -> RunResult:
    """Load the latest ``limit`` files per report from /Reports/Current/."""
    total = RunResult()
    for report in reports:
        urls = _safe_list(source.list_current, report, total)
        if limit > 0:
            urls = urls[-limit:]  # filenames are timestamped, so sorted == chronological
        total.merge(ingest_files(wh, source, report, urls, bronze_dir))
    return total


def run_backfill(
    wh: Warehouse, source, reports: list[Report], start: date, end: date, bronze_dir: Path | None
) -> RunResult:
    """Load daily files from /Reports/Archive/ for an inclusive date range."""
    total = RunResult()
    for report in reports:
        listed = _safe_list(source.list_archive, report, total)
        urls = [u for u in listed if (d := file_date(u)) and start <= d <= end]
        if not urls:
            log.warning("%s: no archive files between %s and %s", report.name, start, end)
        total.merge(ingest_files(wh, source, report, urls, bronze_dir))
    return total
