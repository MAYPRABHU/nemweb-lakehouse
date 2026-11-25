"""Parser for AEMO's multi-table CSV format.

Every NEMWeb CSV mixes several tables in one file, using a record-type prefix:

    C,...                                   comment / file header + footer
    I,DISPATCH,PRICE,5,SETTLEMENTDATE,...   column header for table DISPATCH_PRICE (version 5)
    D,DISPATCH,PRICE,5,"2026/11/24 10:05:00",...   data row

This module turns that into one typed polars DataFrame per table.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict

import polars as pl

DATETIME_FMT = "%Y/%m/%d %H:%M:%S"


def parse_aemo_csv(text: str, wanted: set[str] | None = None) -> dict[str, pl.DataFrame]:
    """Parse one AEMO CSV into ``{table_name: DataFrame}``.

    ``wanted`` limits output to specific tables (others are skipped cheaply).
    If a table's header changes mid-file (new version), both blocks are kept and
    combined with missing columns filled as null.
    """
    current_header: dict[str, tuple[str, ...]] = {}
    blocks: dict[tuple[str, tuple[str, ...]], list[list[str]]] = defaultdict(list)

    for rec in csv.reader(io.StringIO(text)):
        if not rec:
            continue
        kind = rec[0].strip().upper()
        if kind not in ("I", "D") or len(rec) < 4:
            continue
        table = f"{rec[1]}_{rec[2]}".strip().upper()
        if wanted is not None and table not in wanted:
            continue
        if kind == "I":
            current_header[table] = tuple(c.strip().upper() for c in rec[4:])
        else:
            header = current_header.get(table)
            if header is None:
                raise ValueError(f"Data row for {table} appeared before its header row")
            blocks[(table, header)].append(rec[4:])

    per_table: dict[str, list[pl.DataFrame]] = defaultdict(list)
    for (table, header), rows in blocks.items():
        per_table[table].append(_build_frame(header, rows))

    return {
        table: frames[0] if len(frames) == 1 else pl.concat(frames, how="diagonal_relaxed")
        for table, frames in per_table.items()
    }


def _build_frame(header: tuple[str, ...], rows: list[list[str]]) -> pl.DataFrame:
    n = len(header)
    # Defensive: pad short rows / trim long rows so every row matches the header.
    cleaned = [[(v if v != "" else None) for v in (r + [""] * (n - len(r)))[:n]] for r in rows]
    df = pl.DataFrame(cleaned, schema={c: pl.String for c in header}, orient="row")
    return df.select([_infer_type(df.get_column(c)).alias(c) for c in header])


def _infer_type(s: pl.Series) -> pl.Series:
    """Cast a string column to datetime, float, or leave as string.

    Numerics are always Float64 (never Int64) so a later file containing "1.5"
    in a column that happened to look integer can't break the warehouse schema.
    """
    nulls = s.null_count()
    if nulls == s.len():
        return s.cast(pl.Null)
    as_dt = s.str.strptime(pl.Datetime("us"), DATETIME_FMT, strict=False)
    if as_dt.null_count() == nulls:
        return as_dt
    as_float = s.cast(pl.Float64, strict=False)
    if as_float.null_count() == nulls:
        return as_float
    return s
