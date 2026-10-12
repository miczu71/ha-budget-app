"""Skarbonki na kontach-celach (M10 E1)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget import flex, piggy
from budget.snapshot import Snapshot

from .test_categorize_engine import add, conn
from .test_flex import serie

__all__ = ["conn"]

TODAY = date(2026, 10, 3)
PERIOD = date(2026, 9, 24)
NUMBER = "11 2222 3333 4444 5555 6666 7777"  # fikcyjny
DIGITS = "11222233334444555566667777"


def make(c: sqlite3.Connection, **kw: object) -> int:
    args: dict[str, object] = {
        "piggy_id": None,
        "name": "Wakacje",
        "account_number": NUMBER,
        "target": "1200",
        "due_date": "2027-01-15",
        "series_id": None,
        "opening_balance": None,
    }
    args.update(kw)
    return piggy.save(c, **args)  # type: ignore[arg-type]


def move(c: sqlite3.Connection, amount: str, day: str, number: str = "PL" + DIGITS) -> int:
    return add(c, amount, "transfer_out", f"cel {day}", "JA", day=day, counterparty_account=number)


def test_normalize_number() -> None:
    assert piggy.normalize_number(NUMBER) == DIGITS
    assert piggy.normalize_number("pl" + DIGITS) == DIGITS
    with pytest.raises(piggy.PiggyError):
        piggy.normalize_number("12 3456")


def test_save_validates(conn: sqlite3.Connection) -> None:
    with pytest.raises(piggy.PiggyError, match="Bez serii"):
        make(conn, target="")
    pid = make(conn, opening_balance="100")
    assert piggy.get(conn, pid).account_number == DIGITS
    assert piggy.get(conn, pid).masked == "PL** **** … 7777"
    with pytest.raises(piggy.PiggyError, match="już jest"):
        make(conn, name="Inna")  # ten sam numer
    make(conn, piggy_id=pid, name="Urlop", opening_balance="100")
    assert piggy.get(conn, pid).name == "Urlop"


def test_status_from_transfers_and_period(conn: sqlite3.Connection) -> None:
    make(conn, opening_balance="100")
    move(conn, "-200.00", "2026-09-01")  # wpłata przed okresem
    move(conn, "50.00", "2026-08-01")  # wypłata z konta-celu
    move(conn, "-150.00", "2026-09-30", number=NUMBER)  # wpłata w okresie, inny zapis numeru
    move(conn, "-999.00", "2026-09-30", number="PL" + "9" * 26)  # inne konto
    [s] = piggy.statuses(Snapshot(conn), TODAY, PERIOD)
    assert s.balance == Decimal(400) and s.saved == Decimal(150)
    # na początek okresu 250 zł; do 15.01 trzy miesiące odkładania (paź, lis, gru)
    assert s.monthly == Decimal("316.67") and s.to_transfer == Decimal("166.67")
    assert s.progress == pytest.approx(400 / 1200)


def test_no_monthly_after_due_or_when_goal_reached(conn: sqlite3.Connection) -> None:
    make(conn, due_date="2026-09-01")
    make(conn, name="Pełna", account_number="PL" + "8" * 26, opening_balance="1500")
    assert [s.monthly for s in piggy.statuses(Snapshot(conn), TODAY, PERIOD)] == [0, 0]


def test_series_gives_target_and_next_due(conn: sqlite3.Connection) -> None:
    sid = serie(conn, "f1", "480.00", cadence="Y")
    add(conn, "-480.00", "card", "F1", "ODBIORCA f1", day="2026-02-07")
    make(conn, name="F1", target="", due_date="", series_id=sid)
    [s] = piggy.statuses(Snapshot(conn), TODAY, PERIOD)
    assert s.target == Decimal(480) and s.due == date(2027, 2, 7) and s.series_name == "Seria f1"
    assert s.monthly == Decimal(120)  # paź–sty


def test_transfers_and_assigned_spending_stay_out_of_flex(conn: sqlite3.Connection) -> None:
    move(conn, "-300.00", "2026-09-30")  # bez kategorii — dziś liczy się jak elastyczne
    hotel = add(conn, "-700.00", "card", "HOTEL", "HOTEL X", day="2026-09-28")
    add(conn, "-40.00", day="2026-09-29")
    snap = Snapshot(conn)
    assert flex.spent_between(snap, PERIOD, TODAY) == Decimal("1040.00")
    pid = make(conn)
    piggy.assign(conn, hotel, pid)
    assert flex.spent_between(Snapshot(conn), PERIOD, TODAY) == Decimal("40.00")
    [s] = piggy.statuses(Snapshot(conn), TODAY, PERIOD)
    assert s.spent == Decimal(700)
    piggy.assign(conn, hotel, None)
    assert flex.spent_between(Snapshot(conn), PERIOD, TODAY) == Decimal("740.00")


def test_assign_only_expenses(conn: sqlite3.Connection) -> None:
    pid = make(conn)
    income = add(conn, "100.00", "transfer_in", "zwrot", "KTOS")
    with pytest.raises(piggy.PiggyError):
        piggy.assign(conn, income, pid)


def test_archive_hides_piggy(conn: sqlite3.Connection) -> None:
    pid = make(conn)
    piggy.archive(conn, pid)
    assert piggy.all_piggies(conn) == [] and len(piggy.all_piggies(conn, archived=True)) == 1
