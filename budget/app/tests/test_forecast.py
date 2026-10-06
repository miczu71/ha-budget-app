"""Prognoza „czy starczy do wypłaty” (M8 E1)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from budget import flex, forecast
from budget.categorize import engine
from budget.recurring import schedule as sch
from budget.snapshot import Snapshot
from budget.spending import month_start

from .test_categorize_engine import add, conn
from .test_flex import serie
from .test_recurring_schedule import make

__all__ = ["conn"]

TODAY = date(2026, 10, 3)
WAW = ZoneInfo("Europe/Warsaw")


def due(sid: int, day: date, amount: str, direction: str, status: str = sch.EXPECTED) -> sch.Due:
    return sch.Due(make(sid, amount=amount, direction=direction), day, status)


def run(dues: list[sch.Due], free: str = "1000", per_day: str = "10") -> forecast.Projection:
    return forecast.project(
        free_now=Decimal(free), today=TODAY, dues=dues, per_day=Decimal(per_day)
    )


def test_series_flex_and_inflows_up_to_payday() -> None:
    p = run(
        [
            due(1, date(2026, 10, 7), "100", "out"),
            due(2, date(2026, 10, 20), "50", "out"),  # po wypłacie
            due(3, date(2026, 10, 5), "200", "in"),  # wcześniejszy wpływ wchodzi do salda
            due(4, date(2026, 10, 10), "5000", "in"),  # wypłata — poza saldem na jej dzień
        ]
    )
    assert p.payday == date(2026, 10, 10) and p.payday_series == "Seria 4"
    assert [d.series.id for d in p.outflows] == [1]
    assert [d.series.id for d in p.inflows] == [3]
    assert p.flex_total == Decimal("70.00")
    assert p.at_payday == Decimal("1030.00")
    assert (p.low_day, p.low) == (date(2026, 10, 4), Decimal("990.00"))
    assert p.days[0] == (TODAY, Decimal("1000.00")) and len(p.days) == 8


def test_late_outflow_counts_today_late_inflow_is_ignored() -> None:
    p = run(
        [
            due(1, date(2026, 10, 1), "300", "out", sch.LATE),
            due(2, date(2026, 10, 1), "900", "in", sch.LATE),
            due(3, date(2026, 10, 6), "5000", "in"),
        ]
    )
    assert p.payday == date(2026, 10, 6)  # spóźniony wpływ nie jest wypłatą
    assert p.days[0] == (TODAY, Decimal("700.00"))
    assert p.inflows == []
    assert p.at_payday == Decimal("670.00")


def test_without_payday_horizon_is_end_of_month() -> None:
    p = run([due(1, date(2026, 10, 31), "100", "out")], per_day="0")
    assert p.payday is None and p.payday_series is None
    assert p.horizon_end == date(2026, 10, 31)
    assert p.at_payday == Decimal("900.00") and p.low_day == date(2026, 10, 31)


def test_payday_today_is_not_the_horizon() -> None:
    p = run([due(1, TODAY, "5000", "in"), due(2, date(2026, 10, 12), "5000", "in")])
    assert p.payday == date(2026, 10, 12)


def test_skipped_and_paid_dues_do_not_count() -> None:
    p = run(
        [
            due(1, date(2026, 10, 5), "100", "out", sch.PAID),
            due(2, date(2026, 10, 5), "100", "out", sch.SKIPPED),
        ],
        per_day="0",
    )
    assert p.at_payday == Decimal("1000.00") and p.outflows == []


# --- z bazy ------------------------------------------------------------------------------


def snapshot(c: sqlite3.Connection, account: int, kind: str, amount: str, at: str) -> None:
    c.execute(
        "INSERT INTO balance_snapshot (account_id, balance_type, amount, currency, fetched_at) "
        "VALUES (?, ?, ?, 'PLN', ?)",
        (account, kind, amount, at),
    )


def at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=WAW)


def build(
    c: sqlite3.Connection, today: date = TODAY, buffer: str = "0"
) -> forecast.Forecast | None:
    engine.recategorize(c)
    snap = Snapshot(c)
    f = flex.build(snap, month_start(today), today)
    mv = sch.for_month(snap, month_start(today), today)
    return forecast.build(snap, today, at(today.day), f, mv, Decimal(buffer))


def test_build_needs_an_account_balance(conn: sqlite3.Connection) -> None:
    assert build(conn) is None


def test_build_subtracts_card_debt_and_prefers_available(conn: sqlite3.Connection) -> None:
    snapshot(conn, 1, "ITBD", "9321.00", "2026-10-03T10:00:00+02:00")
    snapshot(conn, 1, "ITAV", "9136.98", "2026-10-03T10:00:00+02:00")
    snapshot(conn, 2, "ITBD", "377.67", "2026-10-03T10:00:00+02:00")
    snapshot(conn, 2, "ITAV", "9622.33", "2026-10-03T10:00:00+02:00")
    fc = build(conn)
    assert fc is not None and fc.balances is not None
    assert fc.balances.account == Decimal("9136.98")
    assert fc.balances.card_debt == Decimal("377.67")
    assert fc.free_now == Decimal("8759.31")
    assert fc.stale is False and fc.payday is None


def test_build_without_card_shows_zero_debt_and_marks_stale(conn: sqlite3.Connection) -> None:
    snapshot(conn, 1, "ITAV", "500.00", "2026-10-01T10:00:00+02:00")
    fc = build(conn)
    assert fc is not None and fc.balances is not None
    assert fc.balances.card_debt == 0 and fc.free_now == Decimal("500.00")
    assert fc.stale is True


def test_build_uses_remaining_pool_per_remaining_day(conn: sqlite3.Connection) -> None:
    snapshot(conn, 1, "ITAV", "5000.00", "2026-10-03T10:00:00+02:00")
    flex.set_budget(conn, date(2026, 10, 1), Decimal("3100"))
    add(conn, "-400.00", "card", "LIDL XYZ POL", day="2026-10-02")  # elastyczne; 28 dni do końca
    fc = build(conn)
    assert fc is not None
    assert fc.flex_per_day == Decimal("96.43")  # (3100 − 400) / 28


def test_build_exhausted_pool_uses_current_pace(conn: sqlite3.Connection) -> None:
    snapshot(conn, 1, "ITAV", "5000.00", "2026-10-03T10:00:00+02:00")
    flex.set_budget(conn, date(2026, 10, 1), Decimal("300"))
    add(conn, "-900.00", "card", "LIDL XYZ POL", day="2026-10-02")
    fc = build(conn)
    assert fc is not None
    assert fc.flex_per_day == Decimal("300.00")  # 900 zł przez 3 dni


def test_build_reads_series_from_ledger(conn: sqlite3.Connection) -> None:
    snapshot(conn, 1, "ITAV", "5000.00", "2026-10-03T10:00:00+02:00")
    serie(conn, "czynsz", "800.00")  # termin 7.10
    serie(conn, "pensja", "9000.00", direction="in")
    fc = build(conn)
    assert fc is not None
    assert [d.series.name for d in fc.outflows] == ["Seria czynsz"]
    assert fc.payday == date(2026, 10, 7) and fc.payday_series == "Seria pensja"
    assert fc.at_payday == Decimal("4200.00")  # pensja wpływa 7., dno jest przed nią


def test_build_flags_low_point_below_buffer(conn: sqlite3.Connection) -> None:
    snapshot(conn, 1, "ITAV", "500.00", "2026-10-03T10:00:00+02:00")
    assert build(conn) is not None and not build(conn).below_buffer  # type: ignore[union-attr]
    fc = build(conn, buffer="1000")
    assert fc is not None and fc.below_buffer and fc.buffer == Decimal(1000)


def test_build_looks_into_next_month_when_payday_has_passed(conn: sqlite3.Connection) -> None:
    snapshot(conn, 1, "ITAV", "5000.00", "2026-10-30T10:00:00+02:00")
    serie(conn, "pensja", "9000.00", direction="in")  # termin 7. — w październiku już spóźniony
    serie(conn, "czynsz", "800.00")
    fc = build(conn, today=date(2026, 10, 30))
    assert fc is not None
    assert fc.payday == date(2026, 11, 7)
    assert [d.due for d in fc.outflows] == [
        date(2026, 10, 7),
        date(2026, 11, 7),
    ]  # spóźniony + listopad
