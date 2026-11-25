"""DuckDB warehouse: manifest of processed files + silver tables with key-based upserts.

Schemas:
    meta.processed_files   one row per source zip already loaded (makes reruns idempotent)
    silver.<table>         typed, deduplicated tables, one per AEMO table
    gold.<view>            analytics views (see gold.py)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import polars as pl


def _duck_type(dtype: pl.DataType) -> str:
    if dtype == pl.Datetime or isinstance(dtype, pl.Datetime):
        return "TIMESTAMP"
    if dtype.is_numeric():
        return "DOUBLE"
    return "VARCHAR"


class Warehouse:
    def __init__(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.con = duckdb.connect(str(path))
        for schema in ("meta", "silver", "gold"):
            self.con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS meta.processed_files (
                filename     VARCHAR PRIMARY KEY,
                report       VARCHAR,
                processed_at TIMESTAMP,
                rows_loaded  BIGINT
            )
            """
        )

    # ---- manifest -------------------------------------------------------------------------
    def processed(self, report: str) -> set[str]:
        rows = self.con.execute(
            "SELECT filename FROM meta.processed_files WHERE report = ?", [report]
        ).fetchall()
        return {r[0] for r in rows}

    # ---- tables ---------------------------------------------------------------------------
    def table_exists(self, table: str, schema: str = "silver") -> bool:
        n = self.con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?",
            [schema, table.lower()],
        ).fetchall()[0][0]
        return n > 0

    def load_file(
        self,
        filename: str,
        report: str,
        frames: dict[str, pl.DataFrame],
        keys: dict[str, tuple[str, ...]],
    ) -> dict[str, int]:
        """Upsert every table from one source file and record it in the manifest.

        All of it happens in a single transaction: a file is either fully loaded
        and marked as processed, or not touched at all.
        """
        counts: dict[str, int] = {}
        self.con.execute("BEGIN TRANSACTION")
        try:
            for table, df in frames.items():
                counts[table] = self._upsert(table, df, keys[table])
            self.con.execute(
                "INSERT OR REPLACE INTO meta.processed_files VALUES (?, ?, ?, ?)",
                [
                    filename,
                    report,
                    datetime.now(timezone.utc).replace(tzinfo=None),
                    sum(counts.values()),
                ],
            )
            self.con.execute("COMMIT")
        except Exception:
            self.con.execute("ROLLBACK")
            raise
        return counts

    def _upsert(self, table: str, df: pl.DataFrame, keys: tuple[str, ...]) -> int:
        missing = [k for k in keys if k not in df.columns]
        if missing:
            raise ValueError(f"{table}: key columns missing from data: {missing}")

        # Columns that were null in every row have no type yet; store them as text.
        df = df.with_columns(
            [pl.col(c).cast(pl.String) for c, t in df.schema.items() if t == pl.Null]
        )
        df = df.unique(subset=list(keys), keep="last", maintain_order=True)

        fq = f"silver.{table.lower()}"
        self.con.register("incoming", df.to_arrow())
        try:
            if not self.table_exists(table):
                self.con.execute(f"CREATE TABLE {fq} AS SELECT * FROM incoming")
            else:
                existing = {r[0].upper() for r in self.con.execute(f"DESCRIBE {fq}").fetchall()}
                # Schema evolution: AEMO occasionally adds columns in a new table version.
                for col, dtype in df.schema.items():
                    if col.upper() not in existing:
                        self.con.execute(f'ALTER TABLE {fq} ADD COLUMN "{col}" {_duck_type(dtype)}')
                match = " AND ".join(f't."{k}" = i."{k}"' for k in keys)
                self.con.execute(f"DELETE FROM {fq} AS t USING incoming AS i WHERE {match}")
                self.con.execute(f"INSERT INTO {fq} BY NAME SELECT * FROM incoming")
        finally:
            self.con.unregister("incoming")
        return df.height

    def query(self, sql: str) -> pl.DataFrame:
        return self.con.sql(sql).pl()

    def close(self) -> None:
        self.con.close()
