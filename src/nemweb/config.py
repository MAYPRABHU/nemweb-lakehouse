"""Which NEMWeb reports to ingest, and the natural keys used for upserts.

To add a new table: add it to a report's ``tables`` and give it keys in ``TABLE_KEYS``.
Table names are ``<I-row group>_<I-row subtable>``, e.g. ``I,DISPATCH,PRICE,...`` -> DISPATCH_PRICE.
"""

from __future__ import annotations

from dataclasses import dataclass

BASE_URL = "https://nemweb.com.au"


@dataclass(frozen=True)
class Report:
    name: str  # short name used on the CLI and in the manifest
    folder: str  # folder under /Reports/Current/ and /Reports/Archive/
    tables: tuple[str, ...]  # tables to keep from this report's CSVs

    @property
    def current_url(self) -> str:
        return f"{BASE_URL}/Reports/Current/{self.folder}/"

    @property
    def archive_url(self) -> str:
        return f"{BASE_URL}/Reports/Archive/{self.folder}/"


REPORTS: dict[str, Report] = {
    "dispatchis": Report(
        name="dispatchis",
        folder="DispatchIS_Reports",
        tables=("DISPATCH_PRICE", "DISPATCH_REGIONSUM"),
    ),
    "dispatch_scada": Report(
        name="dispatch_scada",
        folder="Dispatch_SCADA",
        tables=("DISPATCH_UNIT_SCADA",),
    ),
}

# Natural keys, matching the MMS data model primary keys.
TABLE_KEYS: dict[str, tuple[str, ...]] = {
    "DISPATCH_PRICE": (
        "SETTLEMENTDATE",
        "RUNNO",
        "REGIONID",
        "DISPATCHINTERVAL",
        "INTERVENTION",
    ),
    "DISPATCH_REGIONSUM": (
        "SETTLEMENTDATE",
        "RUNNO",
        "REGIONID",
        "DISPATCHINTERVAL",
        "INTERVENTION",
    ),
    "DISPATCH_UNIT_SCADA": ("SETTLEMENTDATE", "DUID"),
}

INTERVAL_MINUTES = 5
