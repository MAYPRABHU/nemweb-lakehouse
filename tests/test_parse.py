import polars as pl
import pytest

from nemweb.fetch import file_date, iter_csvs
from nemweb.parse import parse_aemo_csv
from tests.conftest import FIXTURES, zip_bytes

SAMPLE = (FIXTURES / "PUBLIC_DISPATCHIS_SAMPLE.CSV").read_text()


def test_finds_every_table():
    tables = parse_aemo_csv(SAMPLE)
    assert set(tables) == {"DISPATCH_CASE_SOLUTION", "DISPATCH_PRICE", "DISPATCH_REGIONSUM"}
    assert tables["DISPATCH_PRICE"].height == 5


def test_wanted_filters_tables():
    tables = parse_aemo_csv(SAMPLE, wanted={"DISPATCH_PRICE"})
    assert list(tables) == ["DISPATCH_PRICE"]


def test_types_are_inferred():
    df = parse_aemo_csv(SAMPLE)["DISPATCH_PRICE"]
    assert df.schema["SETTLEMENTDATE"] == pl.Datetime("us")
    assert df.schema["RRP"] == pl.Float64
    assert df.schema["REGIONID"] == pl.String
    assert df.schema["PRICE_STATUS"] == pl.String
    assert df.filter(pl.col("REGIONID") == "SA1")["RRP"].item() == pytest.approx(-35.4)


def test_empty_values_become_null():
    df = parse_aemo_csv(SAMPLE)["DISPATCH_CASE_SOLUTION"]
    assert df["CASESUBTYPE"].null_count() == 1


def test_header_version_change_mid_file_is_combined():
    text = (
        "I,DISPATCH,PRICE,4,SETTLEMENTDATE,REGIONID,RRP\n"
        'D,DISPATCH,PRICE,4,"2026/11/24 10:10:00",NSW1,50\n'
        "I,DISPATCH,PRICE,5,SETTLEMENTDATE,REGIONID,RRP,NEWCOL\n"
        'D,DISPATCH,PRICE,5,"2026/11/24 10:15:00",NSW1,60,x\n'
    )
    df = parse_aemo_csv(text)["DISPATCH_PRICE"]
    assert df.height == 2
    assert df["NEWCOL"].to_list() == [None, "x"]


def test_data_before_header_raises():
    with pytest.raises(ValueError):
        parse_aemo_csv('D,DISPATCH,PRICE,5,"2026/11/24 10:10:00",NSW1,50\n')


def test_iter_csvs_recurses_into_nested_zips():
    inner = zip_bytes({"a.CSV": b"C,hello\n"})
    outer = zip_bytes({"inner.zip": inner, "b.csv": b"C,world\n", "readme.txt": b"skip"})
    names = sorted(name for name, _ in iter_csvs(outer))
    assert names == ["a.CSV", "b.csv"]


@pytest.mark.parametrize(
    "name, expected",
    [
        ("PUBLIC_DISPATCHIS_202611241005_0000000501234567.zip", "2026-11-24"),
        ("https://nemweb.com.au/x/PUBLIC_DISPATCHIS_20261101.zip", "2026-11-01"),
        ("PUBLIC_DISPATCHSCADA_202601010000_0000000123.zip", "2026-01-01"),
        ("something_else.zip", None),
    ],
)
def test_file_date(name, expected):
    d = file_date(name)
    assert (d.isoformat() if d else None) == expected
