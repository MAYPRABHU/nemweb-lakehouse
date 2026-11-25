"""Shared fixtures: build fake NEMWeb folders (Current + nested-zip Archive) on disk."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nemweb.fetch import LocalSource
from nemweb.warehouse import Warehouse

FIXTURES = Path(__file__).parent / "fixtures"
REGIONS = ("NSW1", "QLD1", "SA1", "TAS1", "VIC1")
DUIDS = ("BATT1", "WIND1")


def dispatchis_csv(ts: datetime, price_offset: float = 0.0) -> str:
    s = ts.strftime("%Y/%m/%d %H:%M:%S")
    lines = [
        "C,NEMP.WORLD,DISPATCHIS,AEMO,PUBLIC",
        "I,DISPATCH,PRICE,5,SETTLEMENTDATE,RUNNO,REGIONID,DISPATCHINTERVAL,INTERVENTION,RRP",
    ]
    for i, r in enumerate(REGIONS):
        lines.append(f'D,DISPATCH,PRICE,5,"{s}",1,{r},1,0,{50 + i * 10 + price_offset}')
    lines.append(
        "I,DISPATCH,REGIONSUM,8,SETTLEMENTDATE,RUNNO,REGIONID,DISPATCHINTERVAL,"
        "INTERVENTION,TOTALDEMAND"
    )
    for i, r in enumerate(REGIONS):
        lines.append(f'D,DISPATCH,REGIONSUM,8,"{s}",1,{r},1,0,{1000 + i * 500}')
    lines.append('C,"END OF REPORT"')
    return "\n".join(lines) + "\n"


def scada_csv(ts: datetime) -> str:
    s = ts.strftime("%Y/%m/%d %H:%M:%S")
    lines = [
        "C,NEMP.WORLD,DISPATCHSCADA,AEMO,PUBLIC",
        "I,DISPATCH,UNIT_SCADA,1,SETTLEMENTDATE,DUID,SCADAVALUE",
        f'D,DISPATCH,UNIT_SCADA,1,"{s}",BATT1,-60',
        f'D,DISPATCH,UNIT_SCADA,1,"{s}",WIND1,120',
        'C,"END OF REPORT"',
    ]
    return "\n".join(lines) + "\n"


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def write_current(root: Path, start: datetime, n: int) -> None:
    """n consecutive 5-min Current files for each report."""
    dis = root / "Current" / "DispatchIS_Reports"
    sca = root / "Current" / "Dispatch_SCADA"
    dis.mkdir(parents=True, exist_ok=True)
    sca.mkdir(parents=True, exist_ok=True)
    for k in range(n):
        ts = start + timedelta(minutes=5 * k)
        stamp = ts.strftime("%Y%m%d%H%M")
        name = f"PUBLIC_DISPATCHIS_{stamp}_0000000{k:09d}"
        (dis / f"{name}.zip").write_bytes(zip_bytes({f"{name}.CSV": dispatchis_csv(ts).encode()}))
        sname = f"PUBLIC_DISPATCHSCADA_{stamp}_0000000{k:09d}"
        (sca / f"{sname}.zip").write_bytes(zip_bytes({f"{sname}.CSV": scada_csv(ts).encode()}))


def write_archive_day(root: Path, day: datetime) -> None:
    """One Archive daily zip = 288 inner zips, each holding one CSV (like real NEMWeb)."""
    folder = root / "Archive" / "DispatchIS_Reports"
    folder.mkdir(parents=True, exist_ok=True)
    inner = {}
    for k in range(288):
        ts = day + timedelta(minutes=5 * (k + 1))
        stamp = ts.strftime("%Y%m%d%H%M")
        name = f"PUBLIC_DISPATCHIS_{stamp}_0000000{k:09d}"
        inner[f"{name}.zip"] = zip_bytes({f"{name}.CSV": dispatchis_csv(ts).encode()})
    (folder / f"PUBLIC_DISPATCHIS_{day:%Y%m%d}.zip").write_bytes(zip_bytes(inner))


@pytest.fixture
def wh(tmp_path):
    w = Warehouse(tmp_path / "test.duckdb")
    yield w
    w.close()


@pytest.fixture
def fake_nemweb(tmp_path) -> tuple[Path, LocalSource]:
    root = tmp_path / "nemweb"
    root.mkdir()
    return root, LocalSource(root)
