"""Zmiany serii (M5b E3): inna kwota, spóźniona, ustała — czysta logika + zapis decyzji."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from budget.recurring import changes as ch
from budget.recurring import schedule as sch
from budget.recurring import series as S
from budget.recurring.series import SeriesError
from budget.storage import db

from .test_recurring_schedule import make, tx

TODAY = date(2026, 10, 20)


def kinds(found: list[ch.Change]) -> list[str]:
    return [c.kind for c in found]


def run(s, txns, acks=None, today: date = TODAY) -> list[ch.Change]:
    return ch.detect([s], {s.id: txns}, acks or {}, today)


def monthly(*pairs: tuple[date, str]):
    return [tx(i + 1, d, a) for i, (d, a) in enumerate(pairs)]


OK = [(date(2026, 8, 10), "-100.00"), (date(2026, 9, 10), "-100.00")]


def test_other_amount_outside_tolerance_only() -> None:
    s = make(anchor=10)
    found = run(s, monthly(*OK, (date(2026, 10, 9), "-150.00")))
    assert kinds(found) == [ch.AMOUNT]
    assert found[0].amount == Decimal("150.00") and found[0].period == "2026-10"
    assert run(s, monthly(*OK, (date(2026, 10, 9), "-103.00"))) == []


def test_other_amount_only_last_paid_due_and_recent() -> None:
    s = make(anchor=10)
    # stara kwota z sierpnia nie daje karty, gdy ostatni termin jest w normie
    older = [
        (date(2026, 8, 10), "-150.00"),
        (date(2026, 9, 10), "-100.00"),
        (date(2026, 10, 10), "-100.00"),
    ]
    assert run(s, monthly(*older)) == []
    # ostatni zapłacony termin starszy niż poprzedni miesiąc — bez karty
    old = [(date(2026, 6, 10), "-100.00"), (date(2026, 7, 10), "-150.00")]
    assert ch.AMOUNT not in kinds(run(s, monthly(*old)))


def test_once_ack_hides_amount_card() -> None:
    s = make(anchor=10)
    txns = monthly(*OK, (date(2026, 10, 9), "-150.00"))
    assert run(s, txns, {(1, "2026-10", "amount"): "once"}) == []


def test_late_current_and_previous_month_and_skip() -> None:
    s = make(anchor=10)
    found = run(s, monthly((date(2026, 8, 10), "-100.00"), (date(2026, 9, 10), "-100.00")))
    assert kinds(found) == [ch.LATE] and found[0].period == "2026-10"
    # w oknie (do +5 dni) jeszcze nie spóźniona
    assert run(s, monthly(*OK), today=date(2026, 10, 14)) == []
    # poprzedni miesiąc bez płatności, bieżący zapłacony
    prev = monthly((date(2026, 8, 10), "-100.00"), (date(2026, 10, 10), "-100.00"))
    assert [c.period for c in run(s, prev)] == ["2026-09"]
    # „pomiń ten okres”: karta znika, a termin nie liczy się do „jeszcze zejdzie”
    acks = {(1, "2026-10", "late"): "skip"}
    assert run(s, monthly(*OK), acks) == []
    view = sch.month_view([s], {1: monthly(*OK)}, date(2026, 10, 1), TODAY, acks)
    assert view.rows[0].status == sch.SKIPPED and view.out_planned == 0


def test_stopped_replaces_late_and_keep_hides_until_next_miss() -> None:
    s = make(anchor=10)
    two_missing = monthly((date(2026, 7, 10), "-100.00"), (date(2026, 8, 10), "-100.00"))
    found = run(s, two_missing, today=date(2026, 10, 20))
    # lipiec zapłacony, sierpień… wrzesień i październik bez płatności → ustała, bez „spóźniona”
    assert kinds(found) == [ch.STOPPED] and found[0].period == "2026-10"
    keep = {(1, "2026-10", "stopped"): "keep"}
    assert run(s, two_missing, keep) == []  # keep ukrywa także kartę „spóźniona”
    # następny miesiąc bez płatności = nowy ostatni termin = nowa karta
    assert kinds(run(s, two_missing, keep, today=date(2026, 11, 20))) == [ch.STOPPED]


def test_skip_breaks_the_missing_streak() -> None:
    s = make(anchor=10)
    txns = monthly((date(2026, 8, 10), "-100.00"))
    acks = {(1, "2026-09", "late"): "skip"}
    found = run(s, txns, acks)
    assert kinds(found) == [ch.LATE] and found[0].period == "2026-10"


def test_quarterly_two_misses_is_stopped() -> None:
    s = make(cadence="Q", anchor=None)
    txns = monthly((date(2025, 10, 15), "-100.00"))
    found = run(s, txns, today=date(2026, 10, 20))
    assert kinds(found) == [ch.STOPPED]


def test_new_series_has_no_old_misses_and_ignores_inactive() -> None:
    s = make(anchor=10)
    assert run(s, monthly((date(2026, 10, 12), "-100.00"))) == []
    assert run(make(status="ended"), monthly(*OK)) == []
    assert run(s, []) == []


def test_ack_and_accept_amount_in_db(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "ledger.db")
    sid = S.insert(
        conn,
        name="Seria",
        direction="out",
        cadence="M",
        conditions=make().conditions,
        expected=Decimal("100.00"),
        tolerance=Decimal("5.00"),
        anchor_day=10,
        status="active",
        origin="manual",
        key=None,
    )
    ch.ack(conn, sid, "2026-10", ch.LATE)
    assert sch.acks_from_db(conn) == {(sid, "2026-10", "late"): "skip"}
    ch.accept_amount(conn, sid, Decimal("150"))
    assert S.get(conn, sid).expected_amount == Decimal("150.00")
    with pytest.raises(SeriesError):
        ch.ack(conn, sid, "2026-13", ch.LATE)
    with pytest.raises(SeriesError):
        ch.ack(conn, sid, "2026-10", "nope")
    S.set_status(conn, sid, "end")
    with pytest.raises(SeriesError):
        ch.accept_amount(conn, sid, Decimal("120"))
