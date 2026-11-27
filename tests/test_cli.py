from datetime import datetime

from nemweb.cli import main
from tests.conftest import write_current


def test_run_then_check_passes(tmp_path, capsys):
    # Arrange: fake NEMWeb files
    src = tmp_path / "nemweb"
    write_current(src, datetime(2026, 11, 24, 10, 0), n=3)
    data = tmp_path / "data"

    # Act: load them, then run the quality checks
    assert main(["--data-dir", str(data), "--source-dir", str(src), "run", "--limit", "0"]) == 0
    assert main(["--data-dir", str(data), "check"]) == 0

    # Assert: checks passed
    out = capsys.readouterr().out
    assert "[PASS]" in out


def test_check_on_empty_warehouse(tmp_path, capsys):
    # Arrange: an empty data folder, so nothing has been loaded
    data = tmp_path / "data"

    # Act: run `nemweb check`
    code = main(["--data-dir", str(data), "check"])

    # Assert: it returned 0 and printed the message
    assert code == 0
    assert "nothing to check yet" in capsys.readouterr().out
