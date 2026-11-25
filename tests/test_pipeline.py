from datetime import date, datetime

from nemweb import gold
from nemweb.config import REPORTS
from nemweb.pipeline import run_backfill, run_current
from nemweb.quality import run_checks
from tests.conftest import write_archive_day, write_current

ALL = list(REPORTS.values())


def test_run_current_loads_latest_files(wh, fake_nemweb, tmp_path):
    root, source = fake_nemweb
    write_current(root, datetime(2026, 11, 24, 10, 0), n=6)

    res = run_current(wh, source, ALL, limit=4, bronze_dir=tmp_path / "bronze")

    assert res.files_loaded == 8  # 4 files x 2 reports
    assert res.rows_by_table["DISPATCH_PRICE"] == 4 * 5
    assert res.rows_by_table["DISPATCH_UNIT_SCADA"] == 4 * 2
    assert len(list((tmp_path / "bronze" / "dispatchis").glob("*.zip"))) == 4


def test_rerun_is_idempotent(wh, fake_nemweb):
    root, source = fake_nemweb
    write_current(root, datetime(2026, 11, 24, 10, 0), n=3)
    run_current(wh, source, ALL, limit=0, bronze_dir=None)

    second = run_current(wh, source, ALL, limit=0, bronze_dir=None)

    assert second.files_loaded == 0
    assert second.files_skipped == 6
    assert wh.con.execute("SELECT count(*) FROM silver.dispatch_price").fetchall()[0][0] == 15


def test_backfill_reads_nested_archive_and_passes_checks(wh, fake_nemweb):
    root, source = fake_nemweb
    write_archive_day(root, datetime(2026, 11, 20))
    write_archive_day(root, datetime(2026, 11, 21))

    res = run_backfill(
        wh, source, [REPORTS["dispatchis"]], date(2026, 11, 20), date(2026, 11, 20), bronze_dir=None
    )

    assert res.files_loaded == 1  # only the day asked for
    assert res.rows_by_table["DISPATCH_PRICE"] == 288 * 5
    assert all(c.passed for c in run_checks(wh))

    gold.build_views(wh)
    daily = wh.query("SELECT * FROM gold.daily_region_price WHERE region = 'NSW1'")
    assert daily["intervals"].to_list() == [288]


def test_gold_views_only_built_for_loaded_tables(wh, fake_nemweb):
    root, source = fake_nemweb
    write_current(root, datetime(2026, 11, 24, 10, 0), n=2)
    run_current(wh, source, [REPORTS["dispatch_scada"]], limit=0, bronze_dir=None)

    assert gold.build_views(wh) == ["daily_unit_energy"]
    batt = wh.query("SELECT * FROM gold.daily_unit_energy WHERE duid = 'BATT1'").to_dicts()[0]
    assert batt["energy_in_mwh"] == -10.0  # -60 MW x 2 intervals / 12
