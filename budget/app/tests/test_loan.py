"""Kredyt hipoteczny: harmonogram i zapis (M9 E1)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget import loan

from .test_categorize_engine import conn

__all__ = ["conn"]


def make(c: sqlite3.Connection, **kw: object) -> int:
    args: dict[str, object] = {
        "loan_id": None,
        "name": "Dom",
        "principal": "100000",
        "principal_date": "2026-01-21",
        "reference_rate": "4",
        "margin": "2",
        "installment_kind": "equal",
        "last_payment_date": "2027-01-20",
        "payment_day": "20",
    }
    args.update(kw)
    return loan.save(c, **args)  # type: ignore[arg-type]


def test_payment_dates_clamp_day_and_exclude_start() -> None:
    days = loan.payment_dates(date(2026, 1, 31), date(2026, 4, 30), 31)
    assert days == [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]
    assert loan.payment_dates(date(2026, 1, 20), date(2026, 2, 28), 20) == [date(2026, 2, 20)]


def test_equal_schedule_matches_annuity_and_closes_balance(conn: sqlite3.Connection) -> None:
    lo = loan.get(conn, make(conn))
    rows = loan.schedule(lo)
    assert (
        len(rows) == 12 and rows[0].day == date(2026, 2, 20) and rows[-1].day == date(2027, 1, 20)
    )
    assert rows[-1].balance == Decimal("0.00")
    assert sum(r.principal for r in rows) == Decimal("100000.00")
    # 100 000 zł, 6% rocznie, 12 rat: wzór annuitetowy daje 8606,64 zł
    assert rows[0].payment == pytest.approx(Decimal("8606.64"), abs=Decimal("30"))
    assert loan.summary(rows).installment == rows[0].payment


def test_decreasing_has_constant_principal_and_lower_payments_later(
    conn: sqlite3.Connection,
) -> None:
    lo = loan.get(conn, make(conn, installment_kind="decreasing"))
    rows = loan.schedule(lo)
    assert {r.principal for r in rows[:-1]} == {Decimal("8333.33")}
    assert rows[-1].balance == Decimal("0.00")
    assert rows[0].payment > rows[-2].payment  # odsetki zależą od liczby dni, więc nie co miesiąc


def test_zero_rate_splits_evenly(conn: sqlite3.Connection) -> None:
    lo = loan.get(conn, make(conn, reference_rate="0", margin="0", principal="1200"))
    rows = loan.schedule(lo)
    assert all(r.interest == 0 for r in rows) and rows[0].principal == Decimal("100.00")


def test_save_validates_and_updates(conn: sqlite3.Connection) -> None:
    with pytest.raises(loan.LoanError, match="kapitał"):
        make(conn, principal="0")
    with pytest.raises(loan.LoanError, match="ostatniej raty"):
        make(conn, last_payment_date="2026-01-01")
    with pytest.raises(loan.LoanError, match="dzień raty"):
        make(conn, payment_day="40")
    with pytest.raises(loan.LoanError, match="marżę"):
        make(conn, margin="x")
    lid = make(conn)
    with pytest.raises(loan.LoanError, match="już jest"):
        make(conn, name="Dom")
    make(conn, loan_id=lid, margin="1,7", reference_rate="-0,5")
    lo = loan.get(conn, lid)
    assert lo.rate == Decimal("1.20") and len(loan.all_loans(conn)) == 1
    loan.archive(conn, lid)
    assert loan.all_loans(conn) == []
