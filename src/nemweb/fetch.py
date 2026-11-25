"""Getting files from NEMWeb (or anywhere that looks like it).

A *source* only needs three methods, which keeps the pipeline testable:
``list_current(report)``, ``list_archive(report)`` and ``get(url) -> bytes``.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from nemweb.config import Report

HREF_RE = re.compile(r'href="([^"]+\.zip)"', re.IGNORECASE)
FILE_DATE_RE = re.compile(r"_(\d{8})(?:\d{4})?(?=[_.])")


def file_name(url: str) -> str:
    """Last path segment of a URL or local path, e.g. ``.../PUBLIC_X.zip`` -> ``PUBLIC_X.zip``.

    Splits on both ``/`` and ``\\`` so Windows paths from ``LocalSource`` give a bare file name.
    """
    return re.split(r"[\\/]", url.rstrip("/\\"))[-1]


def file_date(url: str) -> date | None:
    """Date embedded in a NEMWeb filename, e.g. PUBLIC_DISPATCHIS_202611241005_... -> 2026-11-24."""
    m = FILE_DATE_RE.search(file_name(url))
    if not m:
        return None
    d = m.group(1)
    return date(int(d[:4]), int(d[4:6]), int(d[6:]))


def iter_csvs(zip_bytes: bytes) -> Iterator[tuple[str, str]]:
    """Yield ``(name, text)`` for every CSV in a zip, recursing into nested zips (Archive files)."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            lower = info.filename.lower()
            if lower.endswith(".zip"):
                yield from iter_csvs(zf.read(info))
            elif lower.endswith(".csv"):
                yield info.filename, zf.read(info).decode("utf-8", errors="replace")


class HttpSource:
    """Reads directory listings and zip files from nemweb.com.au, with retries and backoff."""

    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(
            total=5,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers["User-Agent"] = "nemweb-lakehouse/0.1 (portfolio project)"

    def _list(self, url: str) -> list[str]:
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return sorted({urljoin(url, href) for href in HREF_RE.findall(resp.text)})

    def list_current(self, report: Report) -> list[str]:
        return self._list(report.current_url)

    def list_archive(self, report: Report) -> list[str]:
        return self._list(report.archive_url)

    def get(self, url: str) -> bytes:
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.content


class LocalSource:
    """Same interface, but reads zips from local folders.

    Layout: <root>/Current/<folder>/ and <root>/Archive/<folder>/.

    Used by the tests, and handy for replaying files you've already downloaded.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _list(self, folder: Path) -> list[str]:
        if not folder.exists():
            return []
        return sorted(str(p) for p in folder.glob("*.zip"))

    def list_current(self, report: Report) -> list[str]:
        return self._list(self.root / "Current" / report.folder)

    def list_archive(self, report: Report) -> list[str]:
        return self._list(self.root / "Archive" / report.folder)

    def get(self, url: str) -> bytes:
        return Path(url).read_bytes()
