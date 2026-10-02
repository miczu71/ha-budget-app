"""CLI księgi na fixture'ach: CSV z Millenetu (zanonimizowany) i zrzuty Mock ASPSP."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from budget import cli
from budget.eb_ingest import hash_digest
from budget.storage import db

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BUDGET_OPTIONS_PATH", str(tmp_path / "brak.json"))
    monkeypatch.setenv("BUDGET_ENV_FILE", str(tmp_path / "brak.env"))
    monkeypatch.setenv("BUDGET_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BUDGET_DEV_DIR", str(tmp_path / "state"))
    return tmp_path


def _mock_state(state: Path) -> None:
    """Sesja i zrzuty jak po `cli auth` + `cli transactions` na Mock ASPSP."""
    session = json.loads((FIXTURES / "eb_mock_session.json").read_text(encoding="utf-8"))
    (state / "sessions").mkdir(parents=True)
    (state / "dumps").mkdir()
    (state / "sessions" / f"{session['session_id']}.json").write_text(json.dumps(session))
    (state / "current_session").write_text(session["session_id"])
    for index, name in ((0, "main"), (2, "savings")):
        digest = hash_digest(session["accounts"][index]["identification_hash"])
        shutil.copy(
            FIXTURES / f"eb_mock_transactions_{name}.json",
            state / "dumps" / f"transactions_{index}_{digest}_20261001T120000Z.json",
        )


def test_ingest_csv_and_report(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["ingest-csv", str(FIXTURES / "millenet_sample.csv")]) == 0
    out = capsys.readouterr().out
    assert "== Księga ==" in out and "== Uzgodnienie salda ==" in out
    assert "#1: OK" in out
    # w raporcie żadnych pełnych numerów kont
    assert not re.search(r"\d{9,}", out.replace(" ", ""))
    assert (env / "data" / "budget.db").is_file()
    # ponowny import: zero nowych wierszy
    assert cli.main(["ingest-csv", str(FIXTURES / "millenet_sample.csv")]) == 0
    assert "nowych 0" in capsys.readouterr().out


def test_ingest_csv_bad_map(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["ingest-csv", str(FIXTURES / "millenet_sample.csv"), "--map", "x"]) == 1
    assert "NUMER=ID_KONTA" in capsys.readouterr().err


def test_ingest_eb_dumps_idempotent(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _mock_state(env / "state")
    dbfile = env / "ledger.db"
    assert cli.main(["ingest-eb", "--db", str(dbfile)]) == 0
    out = capsys.readouterr().out
    assert "nowych 77" in out  # 78 transakcji, w tym 1 oczekująca
    conn = db.connect(dbfile)
    # ten sam IBAN dwa razy w sesji → jedno konto
    assert conn.execute("SELECT count(*) FROM account").fetchone()[0] == 2
    # przelewy rachunek ↔ oszczędnościowe (oba podlinkowane) sparowane
    pairs = conn.execute(
        "SELECT count(*) FROM (SELECT transfer_group FROM txn WHERE transfer_group IS NOT NULL "
        "GROUP BY 1 HAVING count(*) = 2)"
    ).fetchone()[0]
    assert pairs >= 1
    before = conn.execute("SELECT count(*) FROM txn").fetchone()[0]
    assert cli.main(["ingest-eb", "--db", str(dbfile)]) == 0  # zrzuty już wczytane
    assert conn.execute("SELECT count(*) FROM txn").fetchone()[0] == before
