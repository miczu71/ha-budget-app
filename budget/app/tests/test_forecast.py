"""Prognoza „czy starczy do wypłaty” (M8 E1)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from budget import card, flex, forecast, ha_publisher, inbox
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


def run(dues: list[sch.Due], free: str = "1000") -> forecast.Projection:
    return forecast.project(free_now=Decimal(free), today=TODAY, dues=dues)


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
    assert p.at_payday == Decimal("1100.00")  # 1000 + 200 − 100, bez Flex
    assert (p.low_day, p.low) == (TODAY, Decimal("1000.00"))
    assert p.days[0] == (TODAY, Decimal("1000.00")) and len(p.days) == 8


def test_safe_per_day_is_set_by_the_tightest_day() -> None:
    p = run([due(1, date(2026, 10, 5), "400", "out"), due(2, date(2026, 10, 10), "5000", "in")])
    # saldo 600 od 5.10 do 10.10: min(600 / 2 dni do 5.10, 600 / 7 dni do 10.10)
    assert forecast.safe_per_day(p.days, TODAY) == Decimal("85.71")
    assert forecast.safe_per_day(p.days, TODAY, Decimal(100)) == Decimal("71.42")


def test_safe_per_day_negative_when_series_alone_exceed_funds() -> None:
    p = run([due(1, date(2026, 10, 5), "1500", "out"), due(2, date(2026, 10, 10), "5000", "in")])
    assert forecast.safe_per_day(p.days, TODAY) == Decimal("-250.00")  # −500 / 2 dni


def test_safe_per_day_none_without_flex_days() -> None:
    assert forecast.safe_per_day([(TODAY, Decimal(500))], TODAY) is None


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
    assert p.at_payday == Decimal("700.00")


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
    p = run([due(1, date(2026, 10, 31), "100", "out")])
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
    mv = sch.for_month(snap, month_start(today), today)
    return forecast.build(
        snap, today, at(today.day), mv, Decimal(buffer), payday_id, card_debt_included
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


def extra_account(c: sqlite3.Connection, id_: int, kind: str = "current", budget: int = 1) -> None:
    c.execute(
        "INSERT INTO account (id, kind, currency, include_in_budget, created_at) "
        "VALUES (?, ?, 'PLN', ?, '2026-10-01T00:00:00+02:00')",
        (id_, kind, budget),
    )


def test_read_balances_sums_budget_current_accounts(conn: sqlite3.Connection) -> None:
    extra_account(conn, 3)
    snapshot(conn, 1, "ITBD", "1000.00", "2026-10-03T10:00:00+02:00")
    snapshot(conn, 1, "ITAV", "800.00", "2026-10-03T10:00:00+02:00")
    snapshot(conn, 3, "ITBD", "500.00", "2026-10-03T10:00:00+02:00")
    snapshot(conn, 3, "ITAV", "450.00", "2026-10-03T10:00:00+02:00")
    b = forecast.read_balances(conn)
    assert b is not None
    assert b.account == Decimal("1250.00") and b.pending == Decimal("250.00")
    assert b.accounts == 2


def test_read_balances_skips_savings_and_out_of_budget(conn: sqlite3.Connection) -> None:
    extra_account(conn, 3, budget=0)
    extra_account(conn, 4, kind="savings")
    snapshot(conn, 1, "ITAV", "100.00", "2026-10-03T10:00:00+02:00")
    snapshot(conn, 3, "ITAV", "7000.00", "2026-10-03T10:00:00+02:00")
    snapshot(conn, 4, "ITAV", "9000.00", "2026-10-03T10:00:00+02:00")
    b = forecast.read_balances(conn)
    assert b is not None and b.account == Decimal("100.00") and b.accounts == 1


def test_read_balances_missing_snapshot_does_not_zero_the_other(conn: sqlite3.Connection) -> None:
    extra_account(conn, 3)
    snapshot(conn, 3, "ITBD", "300.00", "2026-10-03T10:00:00+02:00")  # konto 1 bez migawki
    b = forecast.read_balances(conn)
    assert b is not None and b.account == Decimal("300.00") and b.accounts == 1


def test_read_balances_fetched_at_is_the_oldest(conn: sqlite3.Connection) -> None:
    extra_account(conn, 3)
    snapshot(conn, 1, "ITAV", "100.00", "2026-10-03T10:00:00+02:00")
    snapshot(conn, 3, "ITAV", "200.00", "2026-10-01T10:00:00+02:00")
    snapshot(conn, 2, "ITBD", "50.00", "2026-10-02T10:00:00+02:00")
    b = forecast.read_balances(conn)
    assert b is not None and b.fetched_at == "2026-10-01T10:00:00+02:00"


def test_read_balances_none_without_any_snapshot(conn: sqlite3.Connection) -> None:
    extra_account(conn, 3)
    snapshot(conn, 2, "ITBD", "50.00", "2026-10-03T10:00:00+02:00")  # tylko karta
    assert forecast.read_balances(conn) is None


def test_build_without_card_shows_zero_debt_and_marks_stale(conn: sqlite3.Connection) -> None:
    snapshot(conn, 1, "ITAV", "500.00", "2026-10-01T10:00:00+02:00")
    fc = build(conn)
    assert fc is not None and fc.balances is not None
    assert fc.balances.card_debt == 0 and fc.free_now == Decimal("500.00")
    assert fc.stale is True


def test_flex_pool_does_not_move_forecast(conn: sqlite3.Connection) -> None:
    # prognoza liczy tylko znane i zaplanowane pozycje — pula Flex (także wyczerpana) jej nie rusza
    snapshot(conn, 1, "ITAV", "5000.00", "2026-10-03T10:00:00+02:00")
    serie(conn, "pensja", "9000.00", direction="in")  # termin 7.
    before = build(conn)
    flex.set_budget(conn, date(2026, 10, 1), Decimal("300"))
    add(conn, "-900.00", "card", "LIDL XYZ POL", day="2026-10-02")  # pula wyczerpana
    fc = build(conn)
    assert before is not None and fc is not None
    assert fc.at_payday == before.at_payday == Decimal("5000.00")
    assert (fc.low_day, fc.low) == (before.low_day, before.low)
    assert fc.safe_per_day == before.safe_per_day


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
    assert [d.series.name for d in fc.inflows] == ["Seria premia"]  # w dniu wypłaty — liczy się
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
    add(conn, "-30.00", day="2026-09-07")  # w dniu wypłaty — już w nowym okresie
    fc = build(conn, payday_id=mine)
    assert fc is not None and fc.payday == date(2026, 10, 7)
    assert fc.period_start == date(2026, 9, 7) and fc.spent_since == Decimal("150.00")
    assert fc.period_elapsed == pytest.approx(26 / 30)  # 7.09 → 7.10, dziś 3.10


def test_without_payday_in_ledger_there_is_no_period(conn: sqlite3.Connection) -> None:
    seeded(conn)
    mine = serie(conn, "pensja", "9000.00", direction="in")
    fc = build(conn, payday_id=mine)
    assert fc is not None and fc.period_start is None and fc.period_elapsed == 0.0


def test_other_inflow_on_payday_counts_like_outflows_that_day() -> None:
    dues = [
        due(1, date(2026, 10, 23), "9000", "in"),  # wypłata
        due(2, date(2026, 10, 23), "800", "in"),  # inny wpływ tego samego dnia
        due(3, date(2026, 10, 23), "100", "out"),
    ]
    p = forecast.project(free_now=Decimal(1000), today=TODAY, dues=dues, payday_id=1)
    assert p.payday == date(2026, 10, 23) and [d.series.id for d in p.inflows] == [2]
    assert p.at_payday == Decimal("1700.00")  # bez samej wypłaty


# --- tygodnie okresu (M21 E4) ---------------------------------------------------------------


def spent_days(a: date, b: date) -> Decimal:
    return Decimal(20 * (b - a).days)  # 20 zł dziennie


def test_weeks_split_period_monday_to_sunday() -> None:
    # ostatnia wypłata w środę 30.09 (jej dzień otwiera okres), następna w czwartek 15.10
    # (jej dzień należy już do następnego okresu), dziś sobota 3.10
    ws = forecast.weeks(
        date(2026, 9, 30), date(2026, 10, 15), TODAY, spent_days, Decimal(30), Decimal(25)
    )
    assert [(w.start, w.end, w.state) for w in ws] == [
        (date(2026, 9, 30), date(2026, 10, 4), forecast.NOW),
        (date(2026, 10, 5), date(2026, 10, 11), forecast.NEXT),
        (date(2026, 10, 12), date(2026, 10, 14), forecast.NEXT),  # dzień przed wypłatą
    ]
    assert [w.days for w in ws] == [5, 7, 3]  # pierwszy i ostatni tydzień przycięte do okresu
    now = ws[0]
    assert now.spent == Decimal(80)  # 30.09–3.10 włącznie z dziś
    assert now.limit == Decimal(105) and now.left == Decimal(25)  # + 25 na niedzielę
    assert ws[1].limit == Decimal(175) and ws[2].limit == Decimal(75) and ws[2].spent == 0


def test_payday_itself_opens_the_new_period() -> None:
    # w dniu wypłaty (wpływ już zaksięgowany) zaczyna się bieżący tydzień nowego okresu
    ws = forecast.weeks(
        date(2026, 10, 3),
        date(2026, 11, 3),
        date(2026, 10, 3),
        spent_days,
        Decimal(30),
        Decimal(25),
    )
    assert ws[0].start == date(2026, 10, 3) and ws[-1].end == date(2026, 11, 2)
    assert ws[0].state == forecast.NOW and ws[0].spent == Decimal(20)  # dzisiejsze wydatki
    assert all(w.state == forecast.NEXT for w in ws[1:]) and sum(w.spent for w in ws[1:]) == 0


def test_weeks_of_a_two_day_period_and_an_empty_one() -> None:
    # wypłata 2.10, następna 4.10: okres to 2.10–3.10 (jeden przycięty tydzień)
    ws = forecast.weeks(date(2026, 10, 2), date(2026, 10, 4), TODAY, spent_days, None, None)
    assert [(w.start, w.end, w.state, w.days) for w in ws] == [
        (date(2026, 10, 2), date(2026, 10, 3), forecast.NOW, 2)
    ]
    # następna wypłata w dniu tej samej wypłaty — okres pusty, bez wyjątku
    assert forecast.weeks(date(2026, 10, 2), date(2026, 10, 2), TODAY, spent_days, None, None) == []


def test_past_weeks_use_plan_and_current_week_uses_todays_limit() -> None:
    today = date(2026, 10, 8)  # czwartek
    ws = forecast.weeks(
        date(2026, 9, 30), date(2026, 10, 15), today, spent_days, Decimal(15), Decimal(5)
    )
    past, now = ws[0], ws[1]
    assert past.state == forecast.PAST and past.limit == Decimal(75) and past.spent == Decimal(100)
    assert past.over and past.used == 1.0  # 30.09–4.10, 5 dni
    assert now.spent == Decimal(80) and now.limit == Decimal(95)  # 5.10–8.10 + 5 × 3 dni
    assert ws[2].limit == Decimal(15)  # 12.10–14.10 × dzisiejsze 5 zł


def test_weeks_without_limit_and_negative_limit() -> None:
    ws = forecast.weeks(date(2026, 10, 1), date(2026, 10, 10), TODAY, spent_days, None, None)
    assert all(w.limit is None for w in ws) and ws[0].left is None
    ws = forecast.weeks(
        date(2026, 10, 1), date(2026, 10, 10), TODAY, spent_days, Decimal(-5), Decimal(-5)
    )
    assert ws[0].limit == ws[0].spent and ws[1].limit == 0  # ujemny limit = nic na kolejne dni


def test_build_has_weeks_and_remembers_period_plan(conn: sqlite3.Connection) -> None:
    seeded(conn)
    mine = serie(conn, "pensja", "9000.00", direction="in")  # termin 7.
    add(conn, "9000.00", "transfer_in", "pensja", "ODBIORCA pensja", day="2026-09-07")
    fc = build(conn, payday_id=mine)
    assert fc is not None and fc.weeks[0].start == date(2026, 9, 7)
    assert fc.weeks[-1].end == date(2026, 10, 6)  # dzień przed następną wypłatą
    assert fc.this_week is not None
    stored = db.kv_get(conn, forecast.PERIOD_PLAN_KEY)
    assert stored == {"start": "2026-09-07", "per_day": str(fc.safe_per_day)}
    assert fc.plan_per_day == fc.safe_per_day
    db.kv_set(conn, forecast.PERIOD_PLAN_KEY, {"start": "2026-09-07", "per_day": "1.00"})
    fc = build(conn, payday_id=mine)
    assert fc is not None and fc.weeks[0].limit == Decimal(7)  # 7.09–13.09 × 1 zł
    assert fc.plan_per_day == Decimal(1)


def test_without_period_there_are_no_weeks(conn: sqlite3.Connection) -> None:
    seeded(conn)
    mine = serie(conn, "pensja", "9000.00", direction="in")
    fc = build(conn, payday_id=mine)
    assert fc is not None and fc.weeks == [] and fc.this_week is None
    assert db.kv_get(conn, forecast.PERIOD_PLAN_KEY) is None


def test_memo_settles_after_period_plan_write(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded(conn)
    mine = serie(conn, "pensja", "9000.00", direction="in")
    add(conn, "9000.00", "transfer_in", "pensja", "ODBIORCA pensja", day="2026-09-07")
    db.kv_set(conn, forecast.PAYDAY_KEY, mine)
    snap, calls = Snapshot(conn), []
    real = forecast.for_today

    def counting(*args: object, **kwargs: object) -> forecast.Forecast | None:
        calls.append(1)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(forecast, "for_today", counting)
    memo = forecast.ForecastMemo()
    for _ in range(4):
        memo.get(snap, TODAY, at(3), Decimal(0))
    assert len(calls) == 2  # zapis `period_plan` zmienia sygnaturę raz


# --- skarbonki w prognozie (M10 E1b) --------------------------------------------------------

GOAL = "11" + "2222" * 6  # fikcyjny numer konta-celu


def piggy_of(c: sqlite3.Connection, **kw: object) -> int:
    from budget import piggy

    args: dict[str, object] = {
        "piggy_id": None,
        "name": "Wakacje",
        "account_number": GOAL,
        "target": "1200",
        "due_date": "2026-12-15",
        "series_id": None,
        "opening_balance": None,
    }
    args.update(kw)
    return piggy.save(c, **args)  # type: ignore[arg-type]


def test_project_takes_piggy_transfer_today() -> None:
    dues = [due(1, date(2026, 10, 10), "5000", "in")]
    plain = run(dues)
    p = forecast.project(free_now=Decimal(1000), today=TODAY, dues=dues, piggy_out=Decimal(300))
    assert p.days[0] == (TODAY, Decimal("700.00")) and p.at_payday == plain.at_payday - 300
    assert [(e.label, e.amount) for e in p.events] == [("Do skarbonek", Decimal(-300))]


def test_project_covered_series_costs_nothing() -> None:
    dues = [due(1, date(2026, 10, 5), "480", "out"), due(2, date(2026, 10, 10), "5000", "in")]
    p = forecast.project(free_now=Decimal(1000), today=TODAY, dues=dues, covered=frozenset({1}))
    assert p.outflows == [] and [e.due.series.id for e in p.events if e.covered and e.due] == [1]
    assert p.at_payday == Decimal(1000) and p.events[0].covered and p.events[0].amount == 0


def test_held_takes_due_outflows_that_fit_in_pending() -> None:
    dues = [
        due(1, date(2026, 10, 2), "300", "out", sch.LATE),
        due(2, TODAY, "5000", "out"),
        due(3, TODAY, "900", "out"),  # nie mieści się już w reszcie
        due(4, date(2026, 10, 4), "10", "out"),  # termin po dniu migawki
        due(5, TODAY, "10", "out", sch.PAID),
        due(6, TODAY, "10", "in"),
    ]
    assert forecast.held(dues, Decimal("5500"), TODAY) == frozenset({1, 2})
    assert forecast.held(dues, Decimal("200"), TODAY) == frozenset()
    assert forecast.held(dues, Decimal(0), TODAY) == frozenset()


def test_project_held_series_costs_nothing() -> None:
    dues = [due(1, TODAY, "5000", "out"), due(2, date(2026, 10, 10), "9000", "in")]
    p = forecast.project(free_now=Decimal(2000), today=TODAY, dues=dues, held=frozenset({1}))
    assert p.outflows == [] and p.at_payday == Decimal(2000)
    assert p.events[0].held and p.events[0].amount == 0 and not p.events[0].covered


def test_build_does_not_count_twice_what_the_bank_already_holds(conn: sqlite3.Connection) -> None:
    serie(conn, "rata", "5000.00")  # termin 7.
    snapshot(conn, 1, "ITBD", "7300.00", "2026-10-07T04:30:00+00:00")
    snapshot(conn, 1, "ITAV", "2000.00", "2026-10-07T04:30:00+00:00")
    fc = build(conn, today=date(2026, 10, 7))
    assert fc is not None and fc.balances is not None
    assert fc.balances.pending == Decimal("5300.00")
    assert [e.due.series.name for e in fc.events if e.held and e.due] == ["Seria rata"]
    assert fc.series_out == 0 and fc.days[0][1] == Decimal("2000.00")


def test_build_snapshot_from_before_due_day_holds_nothing(conn: sqlite3.Connection) -> None:
    serie(conn, "rata", "5000.00")
    snapshot(conn, 1, "ITBD", "7300.00", "2026-10-06T19:30:00+00:00")  # 21:30 dzień wcześniej
    snapshot(conn, 1, "ITAV", "2000.00", "2026-10-06T19:30:00+00:00")
    fc = build(conn, today=date(2026, 10, 7))
    assert fc is not None and not any(e.held for e in fc.events)
    assert fc.series_out == Decimal("5000.00")


def test_build_reserves_piggy_until_transferred(conn: sqlite3.Connection) -> None:
    seeded(conn)
    mine = serie(conn, "pensja", "9000.00", direction="in")  # termin 7.
    before = build(conn, payday_id=mine)
    piggy_of(conn)  # 1200 do 15.12 → paź + lis po 600
    fc = build(conn, payday_id=mine)
    assert before is not None and fc is not None and fc.piggy_out == Decimal(600)
    assert fc.at_payday == before.at_payday - 600
    assert fc.safe_per_day is not None and before.safe_per_day is not None
    assert fc.safe_per_day < before.safe_per_day
    add(conn, "-600.00", "transfer_out", "cel", "JA", day="2026-10-02", counterparty_account=GOAL)
    fc = build(conn, payday_id=mine)
    assert fc is not None and fc.piggy_out == 0


def test_build_series_paid_from_full_piggy(conn: sqlite3.Connection) -> None:
    seeded(conn)
    mine = serie(conn, "pensja", "9000.00", direction="in")
    f1 = serie(conn, "f1", "480.00", cadence="Y")
    add(conn, "-480.00", "card", "F1", "ODBIORCA f1", day="2025-10-05")
    piggy_of(conn, target="", due_date="", series_id=f1, opening_balance="500")
    fc = build(conn, payday_id=mine)
    assert fc is not None
    assert [e.due.series.id for e in fc.events if e.covered and e.due] == [f1]
    assert fc.series_out == 0 and fc.piggy_out == 0


def test_inbox_reminds_about_piggy_before_payday(conn: sqlite3.Connection) -> None:
    seeded(conn)
    mine = serie(conn, "pensja", "9000.00", direction="in")  # za 4 dni
    piggy_of(conn)
    fc = build(conn, payday_id=mine)
    items = inbox.items(Snapshot(conn), at(3), inbox.BalanceMemo(), fc)
    [item] = [i for i in items if i.kind == "piggy_transfer"]
    assert item.link == "/piggy" and "600\xa0zł" in item.detail
    far = build(conn, payday_id=mine, today=date(2026, 10, 1))  # 6 dni do wypłaty
    assert "piggy_transfer" not in [
        i.kind for i in inbox.items(Snapshot(conn), at(1), inbox.BalanceMemo(), far)
    ]


# --- porównanie r/r w hero (M32 E8) ------------------------------------------------------


def _period_with_year_ago(conn: sqlite3.Connection, spent_then: str | None) -> forecast.Forecast:
    seeded(conn)
    mine = serie(conn, "pensja", "9000.00", direction="in")
    add(conn, "9000.00", "transfer_in", "pensja", "ODBIORCA pensja", day="2025-09-07")
    if spent_then is not None:
        add(conn, spent_then, day="2025-09-20")  # rok temu, w okresie 7.09–4.10.2025
    add(conn, "9000.00", "transfer_in", "pensja", "ODBIORCA pensja", day="2026-09-07")
    add(conn, "-120.00", day="2026-09-20")  # bieżący okres: 120 zł, 27 dni
    fc = build(conn, payday_id=mine)
    assert fc is not None and fc.period_start == date(2026, 9, 7)
    return fc


def test_year_ago_less_spent_shows_negative_delta(conn: sqlite3.Connection) -> None:
    fc = _period_with_year_ago(conn, "-200.00")
    assert fc.year_ago_days == 27
    assert fc.spent_year_ago == Decimal("200.00")
    assert fc.yoy_delta == Decimal("-80.00") and fc.yoy_pct == -40


def test_year_ago_more_spent_shows_positive_delta(conn: sqlite3.Connection) -> None:
    fc = _period_with_year_ago(conn, "-50.00")
    assert fc.yoy_delta == Decimal("70.00") and fc.yoy_pct == 140


def test_year_ago_zero_spent_has_no_percent(conn: sqlite3.Connection) -> None:
    fc = _period_with_year_ago(conn, None)
    assert fc.spent_year_ago == Decimal("0")
    assert fc.yoy_delta == Decimal("120.00") and fc.yoy_pct is None


def test_no_payday_a_year_ago_means_no_comparison(conn: sqlite3.Connection) -> None:
    seeded(conn)
    mine = serie(conn, "pensja", "9000.00", direction="in")
    add(conn, "9000.00", "transfer_in", "pensja", "ODBIORCA pensja", day="2026-09-07")
    add(conn, "-120.00", day="2026-09-20")
    fc = build(conn, payday_id=mine)
    assert fc is not None and fc.period_start == date(2026, 9, 7)
    assert fc.spent_year_ago is None and fc.yoy_delta is None and fc.yoy_pct is None


def test_read_balances_card_overpayment_is_negative_debt(conn: sqlite3.Connection) -> None:
    card.set_limit(conn, "10000")
    snapshot(conn, 1, "ITAV", "500.00", "2026-10-03T10:00:00+02:00")
    snapshot(conn, 2, "ITBD", "0.00", "2026-10-03T10:00:00+02:00")
    snapshot(conn, 2, "ITAV", "10100.00", "2026-10-03T10:00:00+02:00")
    b = forecast.read_balances(conn)
    assert b is not None and b.card_debt == Decimal("-100.00")
    fc = build(conn)
    assert fc is not None and fc.free_now == Decimal("600.00")
