"""Prognoza „czy starczy do wypłaty” (M8 E1)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from budget import flex, forecast, ha_publisher, inbox
from budget.categorize import engine
from budget.recurring import schedule as sch
from budget.snapshot import Snapshot
from budget.spending import month_start
from budget.storage import db

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


def test_safe_per_day_is_set_by_the_tightest_day() -> None:
    p = run([due(1, date(2026, 10, 5), "400", "out"), due(2, date(2026, 10, 10), "5000", "in")])
    # dno 10.10: (1000 − 400 − 70) → 10 + 530/7; dzień 5.10: (1000 − 400 − 20) → 10 + 580/2
    assert forecast.safe_per_day(p.days, TODAY, Decimal(10)) == Decimal("85.71")
    assert forecast.safe_per_day(p.days, TODAY, Decimal(10), Decimal(100)) == Decimal("71.42")


def test_safe_per_day_negative_when_series_alone_exceed_funds() -> None:
    p = run([due(1, date(2026, 10, 5), "1500", "out"), due(2, date(2026, 10, 10), "5000", "in")])
    assert forecast.safe_per_day(p.days, TODAY, Decimal(10)) == Decimal("-250.00")


def test_safe_per_day_none_without_flex_days() -> None:
    assert forecast.safe_per_day([(TODAY, Decimal(500))], TODAY, Decimal(10)) is None


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


def test_events_are_signed_chronological_and_late_lands_today() -> None:
    p = run(
        [
            due(1, date(2026, 10, 7), "100", "out"),
            due(2, date(2026, 10, 1), "300", "out", sch.LATE),
            due(3, date(2026, 10, 5), "200", "in"),
            due(4, date(2026, 10, 7), "40", "in"),
            due(5, date(2026, 10, 10), "5000", "in"),  # wypłata — poza listą zdarzeń
            due(6, date(2026, 10, 20), "50", "out"),  # po wypłacie
        ]
    )
    assert [(e.day.day, e.due.series.id, e.amount) for e in p.events] == [
        (3, 2, Decimal(-300)),  # spóźniona → dziś
        (5, 3, Decimal(200)),
        (7, 1, Decimal(-100)),  # tego samego dnia wydatek przed wpływem
        (7, 4, Decimal(40)),
    ]


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
    c: sqlite3.Connection,
    today: date = TODAY,
    buffer: str = "0",
    payday_id: int | None = None,
    card_debt_included: bool = True,
) -> forecast.Forecast | None:
    engine.recategorize(c)
    snap = Snapshot(c)
    f = flex.build(snap, month_start(today), today)
    mv = sch.for_month(snap, month_start(today), today)
    return forecast.build(
        snap, today, at(today.day), f, mv, Decimal(buffer), payday_id, card_debt_included
    )


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


# --- wypłata wskazana przez użytkownika i przełącznik karty (E1b) ------------------------


def test_chosen_series_wins_over_bigger_amount() -> None:
    p = forecast.project(
        free_now=Decimal(1000),
        today=TODAY,
        dues=[
            due(1, date(2026, 10, 10), "9000", "in"),  # większa, ale to nie moja wypłata
            due(2, date(2026, 10, 24), "7000", "in"),
        ],
        per_day=Decimal(0),
        payday_id=2,
    )
    assert p.payday == date(2026, 10, 24) and p.payday_series == "Seria 2"
    assert [d.series.id for d in p.inflows] == [1]  # mniejsza/wcześniejsza wchodzi do salda
    assert p.at_payday == Decimal("10000.00")


def test_build_chosen_payday_moves_to_next_month_and_ignores_stale_choice(
    conn: sqlite3.Connection,
) -> None:
    snapshot(conn, 1, "ITAV", "5000.00", "2026-10-30T10:00:00+02:00")
    mine = serie(conn, "pensja", "9000.00", direction="in")  # termin 7.
    other = serie(conn, "premia", "20000.00", direction="in")  # większa kwota
    engine.recategorize(conn)
    today = date(2026, 10, 30)
    fc = build(conn, today=today, payday_id=mine)
    assert fc is not None and fc.payday == date(2026, 11, 7) and fc.payday_series == "Seria pensja"
    assert fc.inflows == []  # „premia” też wpływa 7.11 — w dniu wypłaty, więc po niej
    assert build(conn, today=today, payday_id=other) is not None
    gone = build(
        conn, today=today, payday_id=9999
    )  # nieistniejąca seria → reguła największej kwoty
    assert gone is not None and gone.payday_series == "Seria premia"


def test_build_without_card_debt(conn: sqlite3.Connection) -> None:
    snapshot(conn, 1, "ITAV", "1000.00", "2026-10-03T10:00:00+02:00")
    snapshot(conn, 2, "ITBD", "400.00", "2026-10-03T10:00:00+02:00")
    with_debt, without = build(conn), build(conn, card_debt_included=False)
    assert with_debt is not None and without is not None
    assert with_debt.free_now == Decimal("600.00") and with_debt.card_debt_included
    assert without.free_now == Decimal("1000.00") and not without.card_debt_included
    assert without.balances is not None and without.balances.card_debt == Decimal("400.00")


def test_settings_read_from_kv(conn: sqlite3.Connection) -> None:
    assert forecast.payday_series_id(conn) is None and forecast.include_card_debt(conn)
    db.kv_set(conn, forecast.PAYDAY_KEY, 7)
    db.kv_set(conn, forecast.CARD_DEBT_KEY, False)
    assert forecast.payday_series_id(conn) == 7 and not forecast.include_card_debt(conn)


# --- encje, dzwonek i memo (E2) -------------------------------------------------------------


def seeded(c: sqlite3.Connection, account: str = "5000.00", debt: str = "400.00") -> None:
    snapshot(c, 1, "ITAV", account, "2026-10-03T10:00:00+02:00")
    snapshot(c, 2, "ITBD", debt, "2026-10-03T10:00:00+02:00")


def test_forecast_entities(conn: sqlite3.Connection) -> None:
    seeded(conn)
    serie(conn, "pensja", "9000.00", direction="in")  # termin 7.
    fc = build(conn, buffer="6000")
    assert fc is not None
    ents = {e.key: e for e in ha_publisher.forecast_entities(fc)}
    assert set(ents) == {
        "forecast_free_now",
        "forecast_card_debt",
        "forecast_lowest",
        "forecast_at_payday",
        "forecast_shortfall",
    }
    assert ents["forecast_free_now"].state == "4600.00"
    assert ents["forecast_card_debt"].state == "400.00"
    assert (
        ents["forecast_lowest"].state == "4600.00"
        and ents["forecast_lowest"].attributes["date"] == TODAY.isoformat()
    )
    assert ents["forecast_at_payday"].attributes["payday"] == "2026-10-07"
    attrs = ents["forecast_at_payday"].attributes
    assert attrs["payday_manual"] is False and attrs["period_start"] is None
    assert attrs["spent_since_payday"] == "0.00" and attrs["safe_per_day"] is not None
    assert ents["forecast_shortfall"].state == "ON"  # 4600 < bufor 6000
    assert ents["forecast_shortfall"].component == "binary_sensor"
    calm = build(conn, buffer="100")
    assert calm is not None
    assert {e.key: e for e in ha_publisher.forecast_entities(calm)}[
        "forecast_shortfall"
    ].state == "OFF"


def test_forecast_entities_card_debt_not_subtracted(conn: sqlite3.Connection) -> None:
    seeded(conn)
    fc = build(conn, card_debt_included=False)
    assert fc is not None
    ents = {e.key: e for e in ha_publisher.forecast_entities(fc)}
    assert ents["forecast_free_now"].state == "5000.00"
    assert ents["forecast_free_now"].attributes["card_debt_included"] is False
    assert ents["forecast_card_debt"].state == "400.00"  # zadłużenie nadal widoczne
    assert ha_publisher.forecast_entities(None) == []


def test_inbox_card_when_below_buffer(conn: sqlite3.Connection) -> None:
    seeded(conn)
    snap = Snapshot(conn)

    def kinds(fc: forecast.Forecast | None) -> list[str]:
        return [i.kind for i in inbox.items(snap, at(3), inbox.BalanceMemo(), fc)]

    assert "forecast_low" not in kinds(build(conn, buffer="100"))
    assert "forecast_low" not in kinds(None)
    below = build(conn, buffer="9000")
    assert "forecast_low" in kinds(below)
    item = next(
        i for i in inbox.items(snap, at(3), inbox.BalanceMemo(), below) if i.kind == "forecast_low"
    )
    assert item.severity == "warn" and "bufor" in item.detail and "03.10" in item.detail
    assert build(conn, buffer="0") is not None and "forecast_low" not in kinds(build(conn))


def test_memo_computes_once_per_database_state(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded(conn)
    snap, calls = Snapshot(conn), []
    real = forecast.for_today

    def counting(*args: object, **kwargs: object) -> forecast.Forecast | None:
        calls.append(1)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(forecast, "for_today", counting)
    memo = forecast.ForecastMemo()
    first = memo.get(snap, TODAY, at(3), Decimal(0))
    assert memo.get(snap, TODAY, at(3), Decimal(0)) is first and len(calls) == 1
    memo.get(snap, TODAY, at(3), Decimal(500))  # inny bufor
    assert len(calls) == 2
    conn.execute("UPDATE balance_snapshot SET amount = '4000.00' WHERE account_id = 1")
    refreshed = memo.get(snap, TODAY, at(3), Decimal(500))  # zmiana bazy
    assert len(calls) == 3 and refreshed is not None and refreshed.free_now == Decimal("3600.00")


# --- ręczna data wypłaty (M21 E1) -----------------------------------------------------------


def test_build_uses_manual_payday_and_reset_restores_series_day(conn: sqlite3.Connection) -> None:
    seeded(conn)
    mine = serie(conn, "pensja", "9000.00", direction="in")  # termin 7.
    serie(conn, "czynsz", "800.00")  # termin 7.
    fc = build(conn, payday_id=mine)
    assert fc is not None and fc.payday == date(2026, 10, 7) and not fc.payday_manual
    assert fc.payday_series_id == mine
    sch.set_override(conn, mine, date(2026, 10, 1), date(2026, 10, 9))
    fc = build(conn, payday_id=mine)
    assert fc is not None and fc.payday == date(2026, 10, 9) and fc.payday_manual
    assert fc.horizon_end == date(2026, 10, 9) and fc.days_left == 6
    sch.set_override(conn, mine, date(2026, 10, 1), None)
    fc = build(conn, payday_id=mine)
    assert fc is not None and fc.payday == date(2026, 10, 7) and not fc.payday_manual


def test_set_override_drops_entries_older_than_three_months(conn: sqlite3.Connection) -> None:
    sch.set_override(conn, 5, date(2026, 6, 1), date(2026, 6, 20))
    sch.set_override(conn, 5, date(2026, 10, 1), date(2026, 10, 23))
    assert sch.overrides_from_db(conn) == {(5, "2026-10"): date(2026, 10, 23)}
    sch.set_override(conn, 5, date(2026, 10, 1), None)
    assert db.kv_get(conn, sch.OVERRIDES_KEY) is None


# --- okres od ostatniej wypłaty (M21 E3) ----------------------------------------------------


def test_period_starts_at_last_payday_and_counts_flexible_spending(
    conn: sqlite3.Connection,
) -> None:
    seeded(conn)
    mine = serie(conn, "pensja", "9000.00", direction="in")  # termin 7.
    add(conn, "9000.00", "transfer_in", "pensja", "ODBIORCA pensja", day="2026-09-07")
    add(conn, "-50.00", day="2026-09-01")  # przed okresem
    add(conn, "-120.00", day="2026-09-20")  # bez kategorii — liczy się jak elastyczne
    fc = build(conn, payday_id=mine)
    assert fc is not None and fc.payday == date(2026, 10, 7)
    assert fc.period_start == date(2026, 9, 7) and fc.spent_since == Decimal("120.00")
    assert fc.period_elapsed == pytest.approx(26 / 30)  # 7.09 → 7.10, dziś 3.10


def test_without_payday_in_ledger_there_is_no_period(conn: sqlite3.Connection) -> None:
    seeded(conn)
    mine = serie(conn, "pensja", "9000.00", direction="in")
    fc = build(conn, payday_id=mine)
    assert fc is not None and fc.period_start is None and fc.period_elapsed == 0.0
