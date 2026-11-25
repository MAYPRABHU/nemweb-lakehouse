from datetime import datetime

import polars as pl

from nemweb.config import TABLE_KEYS


def price_frame(rrp: float, extra: dict | None = None) -> pl.DataFrame:
    data = {
        "SETTLEMENTDATE": [datetime(2026, 11, 24, 10, 10)],
        "RUNNO": [1.0],
        "REGIONID": ["NSW1"],
        "DISPATCHINTERVAL": [1.0],
        "INTERVENTION": [0.0],
        "RRP": [rrp],
    }
    data.update(extra or {})
    return pl.DataFrame(data)


def count(wh):
    return wh.con.execute("SELECT count(*) FROM silver.dispatch_price").fetchall()[0][0]


def test_reloading_same_key_does_not_duplicate(wh):
    wh.load_file("f1.zip", "dispatchis", {"DISPATCH_PRICE": price_frame(50)}, TABLE_KEYS)
    wh.load_file("f2.zip", "dispatchis", {"DISPATCH_PRICE": price_frame(50)}, TABLE_KEYS)
    assert count(wh) == 1


def test_upsert_replaces_value(wh):
    wh.load_file("f1.zip", "dispatchis", {"DISPATCH_PRICE": price_frame(50)}, TABLE_KEYS)
    wh.load_file("f2.zip", "dispatchis", {"DISPATCH_PRICE": price_frame(99)}, TABLE_KEYS)
    assert wh.con.execute("SELECT RRP FROM silver.dispatch_price").fetchall()[0][0] == 99


def test_new_column_is_added(wh):
    wh.load_file("f1.zip", "dispatchis", {"DISPATCH_PRICE": price_frame(50)}, TABLE_KEYS)
    later = price_frame(60, {"REGIONID": ["VIC1"], "NEWCOL": ["hello"]})
    wh.load_file("f2.zip", "dispatchis", {"DISPATCH_PRICE": later}, TABLE_KEYS)
    rows = wh.query("SELECT REGIONID, NEWCOL FROM silver.dispatch_price ORDER BY REGIONID")
    assert rows.to_dicts() == [
        {"REGIONID": "NSW1", "NEWCOL": None},
        {"REGIONID": "VIC1", "NEWCOL": "hello"},
    ]


def test_manifest_records_files(wh):
    wh.load_file("f1.zip", "dispatchis", {"DISPATCH_PRICE": price_frame(50)}, TABLE_KEYS)
    assert wh.processed("dispatchis") == {"f1.zip"}
    assert wh.processed("dispatch_scada") == set()


def test_failed_load_rolls_back_everything(wh):
    bad = pl.DataFrame({"SETTLEMENTDATE": [datetime(2026, 11, 24)]})  # missing key columns
    frames = {"DISPATCH_PRICE": price_frame(50), "DISPATCH_REGIONSUM": bad}
    try:
        wh.load_file("f1.zip", "dispatchis", frames, TABLE_KEYS)
    except ValueError:
        pass
    assert not wh.table_exists("DISPATCH_PRICE")
    assert wh.processed("dispatchis") == set()
