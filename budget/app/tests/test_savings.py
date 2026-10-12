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


def rated(c: sqlite3.Connection, **kw: object) -> savings.Account:
    return savings.get(c, make(c, opening_balance="10000", opening_date="2026-01-01", **kw))


def test_interest_base_rate_capitalizes_monthly_net_of_tax(conn: sqlite3.Connection) -> None:
    acc = rated(conn, base_rate="3.65")  # 0,01% dziennie
    est = savings.estimate(conn, acc, date(2026, 1, 31))  # 30 dni od 2026-01-01
    assert est.earned == Decimal("24.30") and est.accrued == Decimal(0)  # 30 zł × 0,81
    assert est.balance == Decimal("10024.30")
    feb = savings.estimate(conn, acc, date(2026, 2, 10))
    assert feb.accrued > 0 and feb.total == feb.balance + feb.accrued
    assert feb.accrued == Decimal("8.12")  # 10 dni od salda 10024,30 × 0,01% × 0,81


def test_promo_limit_and_end_date(conn: sqlite3.Connection) -> None:
    acc = rated(
        conn, base_rate="0", promo_rate="3.65", promo_limit="5000", promo_until="2026-01-10"
    )
    est = savings.estimate(conn, acc, date(2026, 1, 31))
    assert est.earned == Decimal("3.65")  # 9 dni × 0,50 zł × 0,81, po 10.01 stopa bazowa 0


def test_transfers_change_interest_base(conn: sqlite3.Connection) -> None:
    acc = rated(conn, base_rate="3.65")
    move(conn, "-10000", "2026-01-16")  # wpłata podwaja saldo od 16.01
    est = savings.estimate(conn, acc, date(2026, 1, 31))
    assert est.earned == Decimal("37.26")  # (14 dni × 1 zł + 16 dni × 2 zł) × 0,81


def test_rate_validation(conn: sqlite3.Connection) -> None:
    with pytest.raises(savings.SavingsError, match="stopę bazową"):
        make(conn, base_rate="150")
    with pytest.raises(savings.SavingsError, match="datę końca"):
        make(conn, promo_rate="5")
    aid = make(conn, promo_rate="5", promo_until="2026-12-31", promo_limit="2000", base_rate="2")
    acc = savings.get(conn, aid)
    assert (acc.promo_rate, acc.promo_limit, acc.base_rate) == (5, 2000, 2)
    assert acc.promo_until == date(2026, 12, 31)


def test_promo_bell_and_push(conn: sqlite3.Connection) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from budget import inbox, summary

    make(conn, base_rate="2", promo_rate="5", promo_until="2026-10-20")
    snap = Snapshot(conn)
    waw = ZoneInfo("Europe/Warsaw")

    def kinds(day: int, hour: int = 8) -> list[str]:
        return [m.kind for m in summary.due(snap, datetime(2026, 10, day, hour, 0, tzinfo=waw))]

    assert "savings_promo_1" in kinds(6)  # 14 dni przed
    assert "savings_promo_1" in kinds(17)  # 3 dni przed
    assert "savings_promo_1" not in kinds(10)
    bell = [
        i
        for i in inbox.items(snap, datetime(2026, 10, 10, 9, tzinfo=waw), inbox.BalanceMemo())
        if i.kind == "savings_promo"
    ]
    assert len(bell) == 1 and "kończy się za 10 dni" in bell[0].title
    assert bell[0].link == "/piggy#savings" and "potem 2" in bell[0].detail
    later = datetime(2026, 10, 21, 9, tzinfo=waw)
    assert not [
        i for i in inbox.items(snap, later, inbox.BalanceMemo()) if i.kind == "savings_promo"
    ]
