from datetime import datetime

from nemweb.config import REPORTS
from nemweb.pipeline import run_current
from nemweb.quality import run_checks
from tests.conftest import write_current


def results(wh):
    return {r.name: r for r in run_checks(wh)}


def test_no_data_means_no_checks(wh):
    assert run_checks(wh) == []


def test_gap_in_intervals_is_flagged(wh, fake_nemweb):
    root, source = fake_nemweb
    write_current(root, datetime(2026, 11, 24, 10, 0), n=4)
    # delete the 3rd interval file to simulate a missed run
    files = sorted((root / "Current" / "DispatchIS_Reports").glob("*.zip"))
    files[2].unlink()

    run_current(wh, source, [REPORTS["dispatchis"]], limit=0, bronze_dir=None)

    gap = results(wh)["price_interval_completeness"]
    assert not gap.passed
    assert gap.detail.startswith("5 missing")  # 1 interval x 5 regions
    assert results(wh)["no_duplicate_keys[DISPATCH_PRICE]"].passed
