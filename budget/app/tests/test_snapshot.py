"""Ledger snapshot (M14 E1): wyniki z całej księgi ważne do pierwszego zapisu przez połączenie."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from budget.categorize.rules import Conditions
from budget.recurring import series as S
from budget.service import Service
from budget.snapshot import Snapshot
from budget.storage import db

from .test_categorize_engine import add
from .test_web import client, service
from .test_web_recurring import _account

__all__ = ["client", "service"]


def _seed(conn: sqlite3.Connection) -> None:
    _account(conn)
    for day in ("2026-07-10", "2026-08-10", "2026-09-10"):
        add(conn, "-43.00", "transfer_out", "Abonament", "Qwertyflix Sp", day=day)
    S.insert(
        conn,
        name="Qwertyflix",
        direction="out",
        cadence="M",
        conditions=Conditions(kind="transfer_out", direction="out"),
        expected=Decimal("43"),
        tolerance=Decimal("4"),
        anchor_day=10,
        status="active",
        origin="manual",
        key=None,
    )


@pytest.fixture
def computed(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Liczba prawdziwych przebiegów po księdze (`series.candidates` bez `ids`)."""
    calls: list[int] = []
    real = S.candidates

    def counting(conn: sqlite3.Connection, ids: Sequence[int] | None = None) -> list[S.Candidate]:
        calls.append(1)
        return real(conn, ids)

    monkeypatch.setattr(S, "candidates", counting)
    return calls


def test_candidates_reused_until_write(service: Service, computed: list[int]) -> None:
    conn = service.conn
    _seed(conn)
    snap = Snapshot(conn)
    first = snap.candidates()
    assert snap.candidates() is first
    assert len(computed) == 1 and len(first) == 3

    add(conn, "-43.00", "transfer_out", "Abonament", "Qwertyflix Sp", day="2026-10-02")
    again = snap.candidates()
    assert len(computed) == 2 and len(again) == 4


def test_write_without_new_rows_still_invalidates(service: Service, computed: list[int]) -> None:
    conn = service.conn
    _seed(conn)
    snap = Snapshot(conn)
    snap.candidates()
    conn.execute("UPDATE txn SET description = 'Inny opis'")  # reguły i kategorie też są zapisem
    snap.candidates()
    assert len(computed) == 2


def test_rolled_back_write_is_not_cached(service: Service, computed: list[int]) -> None:
    conn = service.conn
    _seed(conn)
    snap = Snapshot(conn)
    conn.execute("BEGIN")
    add(conn, "-43.00", "transfer_out", "Abonament", "Qwertyflix Sp", day="2026-10-02")
    assert len(snap.candidates()) == 4  # wewnątrz transakcji widać zapis…
    conn.execute("ROLLBACK")
    # …ale po wycofaniu nie zostaje w cache (total_changes po ROLLBACK nie maleje)
    assert len(snap.candidates()) == 3


def test_other_connection_write_invalidates(tmp_path: Path, computed: list[int]) -> None:
    path = tmp_path / "ledger.db"
    one, two = db.connect(path), db.connect(path)
    _seed(one)
    snap = Snapshot(one)
    assert len(snap.candidates()) == 3
    add(two, "-43.00", "transfer_out", "Abonament", "Qwertyflix Sp", day="2026-10-02")
    assert len(snap.candidates()) == 4


async def test_pages_share_one_pass_over_the_ledger(
    client: httpx.AsyncClient, service: Service, computed: list[int]
) -> None:
    _seed(service.conn)
    for path in ("/", "/budget", "/recurring", "/inbox", "/", "/budget"):
        assert (await client.get(path)).status_code == 200
    assert len(computed) == 1, "każda strona liczy przynależność do serii od nowa"
