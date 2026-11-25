from datetime import date

import pytest

from nemweb.fetch import file_date, file_name

NAME = "PUBLIC_DISPATCHIS_202611241005_0000000550000000.zip"


@pytest.mark.parametrize(
    "url",
    [
        f"https://nemweb.com.au/Reports/Current/DispatchIS_Reports/{NAME}",
        f"/home/me/nemweb/Current/DispatchIS_Reports/{NAME}",
        rf"C:\Users\me\nemweb\Current\DispatchIS_Reports\{NAME}",
        rf"C:\Users\me\nemweb\Current/DispatchIS_Reports\{NAME}",
        NAME,
    ],
)
def test_file_name_handles_urls_and_posix_and_windows_paths(url):
    assert file_name(url) == NAME


def test_file_date_ignores_directories_in_windows_paths():
    # The old '/'-only split saw the whole path, and matched the date in the folder name first.
    url = r"C:\nem_20250101_raw\Archive\DispatchIS_Reports\PUBLIC_DISPATCHIS_20261120.zip"
    assert file_date(url) == date(2026, 11, 20)
