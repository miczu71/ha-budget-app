"""Terminy i statusy serii w miesiącu (M5b E2) — czysta logika, bez bazy."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from budget.categorize.rules import Conditions
from budget.recurring import schedule as sch
from budget.recurring.series import Candidate, Series

OCT = date(2026, 10, 1)


def make(
    sid: int = 1,
    cadence: str = "M",
    anchor: int | None = 10,
    amount: str = "100.00",
    direction: str = "out",
    status: str = "active",
) -> Series:
    return Series(
        id=sid,
        name=f"Seria {sid}",
        direction=direction,
        cadence=cadence,
        conditions=Conditions(direction=direction),
        expected_amount=Decimal(amount),
        tolerance=Decimal("5.00"),
        anchor_day=anchor,
        status=status,
        origin="manual",
        group_key=None,
        created_at="2026-01-01T00:00:00",
        decided_at=None,
    )


def tx(tid: int, day: date, amount: str = "-100.00") -> Candidate:
    facts: Any = None
    return Candidate(tid, day, Decimal(amount), "Sprzedawca", "opis", facts)


def view(series: list[Series], txns: dict[int, list[Candidate]], today: date, month: date = OCT):
    return sch.month_view(series, txns, month, today)


def test_monthly_paid_expected_late() -> None:
    s = make(anchor=10)
    paid = view([s], {1: [tx(1, date(2026, 10, 9), "-101.00")]}, date(2026, 10, 20))
    assert [d.status for d in paid.rows] == [sch.PAID]
    assert paid.out_paid == Decimal("101.00") and paid.out_planned == 0
    assert view([s], {}, date(2026, 10, 12)).rows[0].status == sch.EXPECTED
    late = view([s], {}, date(2026, 10, 16))
    assert late.rows[0].status == sch.LATE and late.out_planned == Decimal("100.00")


def test_past_month_without_payment_is_missing_not_planned() -> None:
    v = view([make()], {}, date(2026, 11, 3))
    assert v.rows[0].status == sch.MISSING and v.out_planned == 0


def test_future_month_is_expected() -> None:
    v = view([make()], {}, date(2026, 10, 2), month=date(2026, 12, 1))
    assert v.rows[0].status == sch.EXPECTED and v.out_planned == Decimal("100.00")


def test_anchor_31_clamped_in_february() -> None:
    s = make(anchor=31)
    assert sch.due_date(s, [], date(2026, 2, 1)) == date(2026, 2, 28)


def test_payment_before_month_boundary_counts_to_due_month() -> None:
    s = make(anchor=1)
    early = tx(1, date(2026, 9, 30))
    assert view([s], {1: [early]}, date(2026, 10, 3)).rows[0].status == sch.PAID
    sept = view([s], {1: [early]}, date(2026, 10, 3), month=date(2026, 9, 1))
    assert sept.rows[0].status == sch.MISSING  # 30.09 należy do terminu 1.10, nie 1.09
    assert sept.count(sch.EXTRA) == 1 or sept.out_paid == 0


def test_second_payment_near_due_joins_it() -> None:
    s = make(anchor=2)
    txns = [tx(1, date(2026, 10, 2)), tx(2, date(2026, 10, 12), "-50.00")]
    v = view([s], {1: txns}, date(2026, 10, 30))
    assert [d.status for d in v.rows] == [sch.PAID]
    assert v.out_paid == Decimal("150.00")


def test_payment_outside_any_due_is_extra() -> None:
    s = make(cadence="Q", anchor=None)
    txns = [tx(1, date(2026, 9, 1), "-30.00"), tx(2, date(2026, 9, 28))]
    v = view([s], {1: txns}, date(2026, 9, 30), month=date(2026, 9, 1))
    assert [d.status for d in v.rows] == [sch.EXTRA, sch.PAID]
    assert v.out_paid == Decimal("130.00")


def test_quarterly_due_every_third_month_from_last_occurrence() -> None:
    s = make(cadence="Q", anchor=None)
    last = [tx(1, date(2026, 7, 15))]
    assert sch.due_date(s, last, date(2026, 10, 1)) == date(2026, 10, 15)
    assert sch.due_date(s, last, date(2026, 9, 1)) is None
    assert view([s], {1: last}, date(2026, 10, 5), month=date(2026, 9, 1)).rows == []


def test_yearly_without_history_has_no_due() -> None:
    s = make(cadence="Y", anchor=None)
    assert sch.due_date(s, [], OCT) is None
    assert view([s], {}, date(2026, 10, 5)).rows == []
    hist = [tx(1, date(2025, 10, 20))]
    assert sch.due_date(s, hist, OCT) == date(2026, 10, 20)


def test_only_active_series_and_direction_split() -> None:
    inc = make(2, direction="in", amount="5000.00", anchor=24)
    off = make(3, status="ended")
    v = view([make(), inc, off], {}, date(2026, 10, 2))
    assert [d.series.id for d in v.rows] == [1, 2]
    assert v.out_planned == Decimal("100.00") and v.in_planned == Decimal("5000.00")
    assert v.in_received == 0
