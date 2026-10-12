"""Konto oszczędnościowe poza Enable Banking (M10 E2)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget import piggy, savings
from budget.snapshot import Snapshot

from .test_categorize_engine import add, conn
from .test_piggy import DIGITS, NUMBER, move

__all__ = ["conn"]


def make(c: sqlite3.Connection, **kw: object) -> int:
    args: dict[str, object] = {
        "account_id": None,
        "name": "Oszczędnościowe",
        "account_number": NUMBER,
        "opening_balance": "1000",
        "opening_date": "2026-09-01",
    }
    args.update(kw)
    return savings.save(c, **args)  # type: ignore[arg-type]


def test_save_validates(conn: sqlite3.Connection) -> None:
    with pytest.raises(savings.SavingsError, match="datę"):
        make(conn, opening_date="")
    with pytest.raises(piggy.PiggyError, match="26 cyfr"):
        make(conn, account_number="123")
    aid = make(conn)
    acc = savings.get(conn, aid)
    assert acc.account_number == DIGITS and acc.masked == "PL** **** … 7777"
    with pytest.raises(savings.SavingsError, match="już jest"):
        make(conn, name="Inne")
    make(conn, account_id=aid, account_number="", opening_balance="1500")  # numer bez zmiany
    assert savings.get(conn, aid).account_number == DIGITS
    assert savings.get(conn, aid).opening_balance == Decimal(1500)


def test_balance_from_opening_and_transfers(conn: sqlite3.Connection) -> None:
    acc = savings.get(conn, make(conn))
    move(conn, "-200", "2026-08-20")  # przed datą salda — już w nim
    move(conn, "-300", "2026-09-10")  # wpłata
    move(conn, "100", "2026-09-20")  # wypłata
    assert savings.balance(conn, acc) == Decimal(1200)


def test_transfers_are_outside_flex_pool(conn: sqlite3.Connection) -> None:
    make(conn)
    tid = move(conn, "-300", "2026-09-10")
    other = add(conn, "-20", "card", "kawa", "KAWIARNIA", day="2026-09-11")
    ids = Snapshot(conn).piggy_ids()
    assert tid in ids and other not in ids
    assert savings.txn_ids(conn) == {tid}


def test_archive_hides_account(conn: sqlite3.Connection) -> None:
    aid = make(conn)
    savings.archive(conn, aid)
    assert savings.all_accounts(conn) == []
    with pytest.raises(savings.SavingsError):
        savings.archive(conn, 999)
    assert date(2026, 9, 1) == savings.get(conn, aid).opening_date
