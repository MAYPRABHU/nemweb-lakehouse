"""Data quality checks. Each returns a CheckResult; the CLI exits non-zero if any fail."""

from __future__ import annotations

from dataclasses import dataclass

from nemweb.config import INTERVAL_MINUTES, TABLE_KEYS
from nemweb.warehouse import Warehouse


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def check_no_duplicate_keys(wh: Warehouse) -> list[CheckResult]:
    results = []
    for table, keys in TABLE_KEYS.items():
        if not wh.table_exists(table):
            continue
        cols = ", ".join(f'"{k}"' for k in keys)
        dupes = wh.con.execute(
            f"SELECT count(*) FROM (SELECT {cols} FROM silver.{table.lower()} "
            f"GROUP BY {cols} HAVING count(*) > 1)"
        ).fetchall()[0][0]
        results.append(
            CheckResult(f"no_duplicate_keys[{table}]", dupes == 0, f"{dupes} duplicated key(s)")
        )
    return results


def check_price_interval_gaps(wh: Warehouse) -> list[CheckResult]:
    """Every region should have a price for every 5-min interval between the first and last load."""
    if not wh.table_exists("DISPATCH_PRICE"):
        return []
    row = wh.con.execute(
        f"""
        WITH prices AS (
            SELECT SETTLEMENTDATE, REGIONID FROM silver.dispatch_price WHERE INTERVENTION = 0
        ),
        bounds AS (SELECT min(SETTLEMENTDATE) AS lo, max(SETTLEMENTDATE) AS hi FROM prices),
        expected AS (
            SELECT unnest(generate_series(lo, hi, INTERVAL {INTERVAL_MINUTES} MINUTE)) AS ts
            FROM bounds
        ),
        regions AS (SELECT DISTINCT REGIONID FROM prices)
        SELECT count(*), any_value(e.ts ORDER BY e.ts)
        FROM expected e CROSS JOIN regions r
        ANTI JOIN prices p ON p.SETTLEMENTDATE = e.ts AND p.REGIONID = r.REGIONID
        """
    ).fetchall()[0]
    missing, first_gap = row
    detail = f"{missing} missing region-interval(s)"
    if missing:
        detail += f", first at {first_gap} — run `nemweb backfill` for that date"
    return [CheckResult("price_interval_completeness", missing == 0, detail)]


def check_price_not_null(wh: Warehouse) -> list[CheckResult]:
    if not wh.table_exists("DISPATCH_PRICE"):
        return []
    sql = "SELECT count(*) FROM silver.dispatch_price WHERE RRP IS NULL"
    n = wh.con.execute(sql).fetchall()[0][0]
    return [CheckResult("price_not_null", n == 0, f"{n} row(s) with null RRP")]


def run_checks(wh: Warehouse) -> list[CheckResult]:
    return [
        *check_no_duplicate_keys(wh),
        *check_price_interval_gaps(wh),
        *check_price_not_null(wh),
    ]
