"""Raport księgi jako dane (panel) i jako tekst (CLI) — te same liczby."""

from __future__ import annotations

import re
from pathlib import Path

from budget import ledger, report
from budget.storage import db

FIXTURES = Path(__file__).parent / "fixtures"


def _ledger() -> db.sqlite3.Connection:
    conn = db.connect(":memory:")
    ledger.ingest_csv(
        conn,
        (FIXTURES / "millenet_sample.csv").read_bytes(),
        file_name="millenet_sample.csv",
        fetched_at="2026-10-01T12:00:00+00:00",
        card_map={},
    )
    return conn


def test_empty_ledger() -> None:
    rep = report.build(db.connect(":memory:"))
    assert rep.accounts == []
    assert rep.csv_rows == []
    assert rep.transfer_pairs == 0 and rep.transfer_unpaired == 0
    assert rep.balance_checks == []


def test_report_counts_match_ledger() -> None:
    conn = _ledger()
    rep = report.build(conn)
    total = conn.execute("SELECT count(*) FROM txn WHERE status = 'BOOK'").fetchone()[0]
    assert sum(s.count for a in rep.accounts for s in a.sources) == total
    assert (
        sum(r.count for r in rep.csv_rows)
        == conn.execute("SELECT count(*) FROM csv_row").fetchone()[0]
    )
    assert sum(rep.kind_sources.values()) == conn.execute("SELECT count(*) FROM txn").fetchone()[0]
    assert rep.balance_checks and rep.balance_checks[0].ok
    # maskowany IBAN — nigdy pełny numer
    for acc in rep.accounts:
        assert acc.iban_masked is None or not re.search(r"\d{9,}", acc.iban_masked)


def test_text_report_has_no_full_numbers() -> None:
    lines = report.format_text(report.build(_ledger()))
    text = "\n".join(lines)
    assert "== Księga ==" in text and "== Uzgodnienie salda ==" in text
    assert "#1: OK" in text
    assert not re.search(r"\d{9,}", text.replace(" ", ""))
