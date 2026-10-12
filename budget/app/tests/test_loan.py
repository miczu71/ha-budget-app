"""Kredyt hipoteczny: harmonogram i zapis (M9 E1)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

import pytest

from budget import ha_publisher, inbox, loan
from budget.categorize.rules import Conditions
from budget.recurring import series as S
from budget.snapshot import Snapshot

from .test_categorize_engine import add, conn

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
    assert loan.payment_dates(date(2026, 1, 20), date(2026, 3, 28), 20) == [
        date(2026, 2, 20),
        date(2026, 3, 28),  # ostatnia rata w dniu końca kredytu, nie w dniu raty
    ]


def test_interest_is_30_360_and_last_period_is_prorated(conn: sqlite3.Connection) -> None:
    lo = loan.get(
        conn,
        make(
            conn,
            principal="100000",
            principal_date="2026-01-20",
            reference_rate="4",
            margin="2",
            last_payment_date="2026-04-04",
        ),
    )
    rows = loan.schedule(lo)
    # pełny miesiąc: saldo × 6% / 12, niezależnie od liczby dni w miesiącu
    assert rows[0].interest == Decimal("500.00")
    assert rows[1].interest == (rows[0].balance * Decimal("0.005")).quantize(Decimal("0.01"))
    # ostatni okres 20.03 → 4.04 = 14 dni / 360
    assert rows[-1].day == date(2026, 4, 4)
    assert rows[-1].interest == (rows[-2].balance * Decimal("0.06") * 14 / 360).quantize(
        Decimal("0.01")
    )
    assert rows[-1].balance == Decimal("0.00")


def test_bank_installment_is_the_level_and_last_installment_closes(
    conn: sqlite3.Connection,
) -> None:
    lo = loan.get(conn, make(conn, installment="8600.00"))
    assert lo.installment == Decimal("8600.00")
    rows = loan.schedule(lo)
    assert {r.payment for r in rows[:-1]} == {Decimal("8600.00")}
    assert rows[-1].balance == Decimal("0.00")
    with pytest.raises(loan.LoanError):
        make(conn, name="Inny", installment="-5")
    assert loan.get(conn, make(conn, name="Trzeci", installment="  ")).installment is None


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
    assert loan.summary(lo, rows, date(2026, 1, 21)).installment == rows[0].payment


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


def test_summary_is_as_of_today(conn: sqlite3.Connection) -> None:
    lo = loan.get(conn, make(conn))
    rows = loan.schedule(lo)
    before = loan.summary(lo, rows, date(2026, 1, 21))
    assert before.principal == Decimal("100000.00") and before.count == 12
    mid = loan.summary(lo, rows, date(2026, 3, 25))  # po ratach 20.02 i 20.03
    assert mid.principal == rows[1].balance and mid.count == 10
    assert mid.installment == rows[2].payment and mid.payoff == date(2027, 1, 20)
    done = loan.summary(lo, rows, date(2027, 2, 1))
    assert done.principal == Decimal("0.00") and done.count == 0 and done.installment == 0


def test_drift_flags_changed_installment_only() -> None:
    lo = loan.Loan(
        1,
        "Dom",
        Decimal(100000),
        date(2026, 1, 21),
        Decimal(4),
        Decimal(2),
        "equal",
        date(2027, 1, 20),
        20,
    )
    rows = loan.schedule(lo)
    exp = rows[0].payment
    assert loan.drift(rows, date(2026, 2, 21), exp) is None
    assert loan.drift(rows, date(2026, 2, 21), exp + Decimal("0.50")) is None  # < 1%
    d = loan.drift(rows, date(2026, 2, 21), exp * Decimal("1.1"))
    assert d is not None and d.expected == exp
    assert loan.drift(rows, date(2026, 6, 5), exp * 2) is None  # daleko od dnia raty
    assert loan.drift([], date(2026, 2, 21), exp) is None


def _series(conn: sqlite3.Connection, direction: str = "out") -> int:
    return S.insert(
        conn,
        name="Rata",
        direction=direction,
        cadence="M",
        conditions=Conditions(),
        expected=Decimal("100"),
        tolerance=Decimal("10"),
        anchor_day=20,
        status="active",
        origin="manual",
        key=None,
    )


def test_set_series_rejects_income_and_unlinks(conn: sqlite3.Connection) -> None:
    lid = make(conn)
    with pytest.raises(loan.LoanError, match="wydatkowa"):
        loan.set_series(conn, lid, _series(conn, "in"))
    sid = _series(conn)
    loan.set_series(conn, lid, sid)
    assert loan.get(conn, lid).series_id == sid
    make(conn, loan_id=lid, margin="1")  # zapis parametrów nie odpina serii
    assert loan.get(conn, lid).series_id == sid
    loan.set_series(conn, lid, None)
    assert loan.get(conn, lid).series_id is None


def test_inbox_card_and_entity(conn: sqlite3.Connection) -> None:
    lid = make(conn)
    rows = loan.schedule(loan.get(conn, lid))
    loan.set_series(conn, lid, _series(conn))
    now = datetime(2026, 3, 1, 9, 0)

    def cards() -> list[inbox.Item]:
        items = inbox.items(Snapshot(conn), now, inbox.BalanceMemo())
        return [i for i in items if i.kind == "loan_rate"]

    add(conn, str(-rows[0].payment), kind="loan", day="2026-02-20", description="rata")
    assert cards() == []
    add(conn, str(-rows[1].payment * 2), kind="loan", day="2026-03-20", description="rata")
    (card,) = cards()
    assert card.link == f"/loan?edit={lid}#edit-loan" and "harmonogramie" in card.detail
    (ent,) = ha_publisher.loan_entities(conn, date(2026, 3, 25))
    assert ent.key == "loan_principal" and ent.state == str(rows[1].balance)
    assert ent.attributes["installments_left"] == 10 and ent.attributes["rate"] == "6.00"
