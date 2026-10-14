"""Prognoza roczna (M18 E1): rdzeń `year.project` bez bazy."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget import year
from budget.categorize import engine, taxonomy
from budget.recurring import schedule as sch
from budget.service import Service
from budget.snapshot import Snapshot
from budget.spending import add_months
from budget.storage import db

from .test_categorize_engine import conn
from .test_flex import serie, spend
from .test_forecast import snapshot
from .test_recurring_schedule import make
from .test_web import _client, service

__all__ = ["conn", "service"]

TODAY = date(2026, 10, 14)
D = Decimal


def due(sid: int, day: date, amount: str, direction: str, status: str = sch.EXPECTED) -> sch.Due:
    return sch.Due(make(sid, amount=amount, direction=direction), day, status)


def run(
    dues: dict[date, list[sch.Due]] | None = None,
    start: str = "1000",
    today: date = TODAY,
    **kw: object,
) -> year.Projection:
    params: dict[str, object] = {
        "flex": D(0),
        "irregular": D(0),
        "seasonal": {},
        "buffer": D(0),
        "target": D(0),
    }
    params.update(kw)
    return year.project(start_balance=D(start), today=today, dues=dues or {}, **params)  # type: ignore[arg-type]


def test_horizon_ends_in_december_until_october() -> None:
    assert year.horizon_end(date(2026, 10, 14)) == date(2026, 12, 31)
    assert year.horizon_end(date(2026, 1, 1)) == date(2026, 12, 31)


def test_horizon_covers_next_year_from_november() -> None:
    assert year.horizon_end(date(2026, 11, 1)) == date(2027, 12, 31)
    assert year.horizon_end(date(2026, 12, 31)) == date(2027, 12, 31)


def test_months_start_with_current_and_reach_horizon_end() -> None:
    p = run()
    assert [m.month for m in p.months] == [date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1)]
    p = run(today=date(2026, 11, 3))
    assert p.months[0].month == date(2026, 11, 1) and p.months[-1].month == date(2027, 12, 1)
    assert len(p.months) == 14


def test_current_month_counts_only_pending_series_and_pro_rata_flex() -> None:
    dues = {
        date(2026, 10, 1): [
            due(1, date(2026, 10, 5), "300", "out", sch.PAID),  # już w saldzie
            due(2, date(2026, 10, 20), "100", "out"),
            due(3, date(2026, 10, 10), "50", "out", sch.LATE),  # spóźniona schodzi
            due(4, date(2026, 10, 25), "400", "in"),
            due(5, date(2026, 10, 12), "999", "in", sch.LATE),  # nie wiadomo, kiedy wpłynie
        ]
    }
    m = run(dues, flex=D("310")).months[0]
    assert (m.inflow, m.series_out) == (D("400"), D("150"))
    # 17 z 31 dni miesiąca zostało po dzisiejszym dniu
    assert m.flex == D("170.00")
    assert m.balance == D("1000") + 400 - 150 - D("170.00")


def test_future_month_uses_all_series_and_full_flex() -> None:
    dues = {
        date(2026, 11, 1): [
            due(1, date(2026, 11, 3), "700", "out"),
            due(2, date(2026, 11, 24), "5000", "in"),
        ]
    }
    p = run(dues, flex=D("1000"), irregular=D("100"), seasonal={date(2026, 11, 1): D("250")})
    nov = p.months[1]
    assert (nov.inflow, nov.series_out, nov.flex, nov.irregular, nov.seasonal) == (
        D("5000"),
        D("700"),
        D("1000"),
        D("100"),
        D("250"),
    )
    assert nov.net == D("2950.00")


def test_balance_is_cumulative_and_end_is_last_month() -> None:
    p = run(flex=D("100"), start="500")
    assert [m.balance for m in p.months][1:] == [
        p.months[0].balance - 100,
        p.months[0].balance - 200,
    ]
    assert p.end == p.months[-1].balance


def test_first_deficit_is_first_month_below_buffer() -> None:
    dues = {date(2026, 12, 1): [due(1, date(2026, 12, 5), "2000", "out")]}
    p = run(dues, start="1000", buffer=D("100"))
    assert p.first_deficit == date(2026, 12, 1)
    assert [m.below_buffer for m in p.months] == [False, False, True]
    assert run(start="1000").first_deficit is None


def test_max_flex_is_set_by_the_tightest_month() -> None:
    dues = {date(2026, 11, 1): [due(1, date(2026, 11, 3), "900", "out")]}
    p = run(dues, start="1000", buffer=D("100"), target=D("0"))
    # Listopad: 1000 − 900 − F·(17/31 + 1) ≥ 100 → F ≤ 0; grudzień rządzony tym samym kapitałem
    assert p.max_flex == D("0.00")


def test_max_flex_respects_target_at_end_of_horizon() -> None:
    p = run(start="3100", buffer=D("0"), target=D("100"))
    w = D(17) / 31 + 2  # ułamek bieżącego miesiąca + dwa pełne
    assert p.max_flex == ((D("3100") - 100) / w).quantize(D("0.01"), rounding="ROUND_FLOOR")


def test_max_flex_negative_when_series_alone_break_buffer() -> None:
    dues = {date(2026, 10, 1): [due(1, date(2026, 10, 20), "1500", "out")]}
    assert run(dues, start="1000").max_flex < 0


def test_target_below_buffer_does_not_loosen_buffer() -> None:
    p = run(start="1000", buffer=D("500"), target=D("0"))
    assert p.max_flex == (D("500") / (D(17) / 31 + 2)).quantize(D("0.01"), rounding="ROUND_FLOOR")


# --- z bazy ------------------------------------------------------------------------------


def balance(c: sqlite3.Connection, amount: str = "5000.00") -> None:
    snapshot(c, 1, "ITAV", amount, "2026-10-14T08:00:00+02:00")


def months(first: date, n: int) -> list[str]:
    return [f"{add_months(first, i):%Y-%m}" for i in range(n)]


def seeded(c: sqlite3.Connection) -> Snapshot:
    """12 pełnych miesięcy do września 2026: Flex 100 zł (w marcu 1300), ubezpieczenie w grudniu."""
    for m in months(date(2025, 10, 1), 12):
        spend(c, "1300.00" if m == "2026-03" else "100.00", m, "spozywcze")
    spend(c, "600.00", "2025-12", "ubezpieczenia")
    engine.recategorize(c)
    balance(c)
    return Snapshot(c)


def test_lookback_skips_current_and_future_months() -> None:
    assert year._lookback(date(2026, 12, 1), date(2026, 10, 14)) == date(2025, 12, 1)
    assert year._lookback(date(2027, 11, 1), date(2026, 11, 3)) == date(2025, 11, 1)
    assert year._lookback(date(2026, 3, 1), date(2026, 10, 14)) == date(2026, 3, 1)


def test_history_median_irregular_and_seasonal(conn: sqlite3.Connection) -> None:
    h = year.history(seeded(conn), TODAY)
    assert (h.months, h.flex, h.irregular) == (12, D("100.00"), D("100.00"))
    assert h.seasonal[date(2026, 12, 1)] == D("600.00")
    assert h.seasonal[date(2026, 11, 1)] == D("0.00")


def test_seasonal_ignores_payments_covered_by_a_series(conn: sqlite3.Connection) -> None:
    seeded(conn)
    serie(conn, "ubezpieczenia", "600.00", cadence="Y")
    assert year.history(Snapshot(conn), TODAY).seasonal[date(2026, 12, 1)] == D("0.00")


def skip_category(c: sqlite3.Connection, slug: str) -> None:
    cat = next(x for x in taxonomy.all_categories(c).values() if x.slug == slug)
    taxonomy.set_year_skip(c, cat.id, True)


def test_skipped_flexible_category_leaves_median_and_irregular(conn: sqlite3.Connection) -> None:
    snap = seeded(conn)
    spend(conn, "9000.00", "2025-11", "paliwo")
    engine.recategorize(conn)
    before = year.history(snap, TODAY)
    assert (before.flex, before.irregular) == (D("100.00"), D("850.00"))
    skip_category(conn, "paliwo")
    after = year.history(snap, TODAY)
    assert (after.flex, after.irregular) == (D("100.00"), D("100.00"))
    assert after.skipped == D("750.00")  # 9000 / 12 miesięcy
    assert after.skipped_names == ["Paliwo"]


def test_skipped_non_monthly_category_leaves_seasonal(conn: sqlite3.Connection) -> None:
    snap = seeded(conn)
    skip_category(conn, "ubezpieczenia")
    h = year.history(snap, TODAY)
    assert h.seasonal[date(2026, 12, 1)] == D("0.00")
    assert h.skipped == D("50.00")  # 600 / 12 miesięcy


def test_skipped_empty_without_flags(conn: sqlite3.Connection) -> None:
    h = year.history(seeded(conn), TODAY)
    assert (h.skipped, h.skipped_names) == (D("0"), [])


def test_history_empty_without_ledger(conn: sqlite3.Connection) -> None:
    assert year.history(Snapshot(conn), TODAY) == year.History()


def test_build_needs_an_account_balance(conn: sqlite3.Connection) -> None:
    assert year.build(Snapshot(conn), TODAY) is None


def test_build_combines_history_balance_and_pro_rata(conn: sqlite3.Connection) -> None:
    p = year.build(seeded(conn), TODAY, D("200"))
    assert p is not None
    assert (p.start_balance, p.flex_month, p.flex_manual, p.history_months) == (
        D("5000.00"),
        D("100.00"),
        False,
        12,
    )
    now, _, dec = p.months
    assert (now.flex, now.irregular) == (D("54.84"), D("54.84"))
    assert dec.seasonal == D("600.00")
    assert p.buffer == D("200")


def test_build_manual_flex_replaces_median_and_irregular(conn: sqlite3.Connection) -> None:
    snap = seeded(conn)
    db.kv_set(conn, year.FLEX_KEY, "250")
    db.kv_set(conn, year.TARGET_KEY, "1000")
    p = year.build(snap, TODAY)
    assert p is not None and p.flex_manual and p.target == D("1000")
    assert p.flex_month == D("250") and p.months[1].flex == D("250.00")
    assert all(m.irregular == 0 for m in p.months)


# --- backtest (pomiar w add-onie) ---------------------------------------------------------


def test_backtest_compares_non_series_spend_with_forecast_from_december(
    conn: sqlite3.Connection,
) -> None:
    for m in months(date(2024, 12, 1), 15):  # do lutego 2026
        spend(conn, "100.00", m, "spozywcze")
    spend(conn, "50.00", "2026-02", "spozywcze")
    engine.recategorize(conn)
    out = year.backtest(Snapshot(conn), date(2026, 3, 10), "2026-03-10T08:00:00+01:00")
    assert [(r["month"], r["predicted"], r["actual"]) for r in out["months"]] == [
        ("2026-01", "100.00", "100.00"),
        ("2026-02", "100.00", "150.00"),
    ]
    assert (out["predicted"], out["actual"], out["error_pct"]) == ("200.00", "250.00", -20.0)
    assert out["history_months"] == 12 and not out["within_10"]


def test_backtest_leaves_out_skipped_categories(conn: sqlite3.Connection) -> None:
    snap = seeded(conn)
    spend(conn, "500.00", "2026-02", "paliwo")
    engine.recategorize(conn)
    skip_category(conn, "paliwo")
    out = year.backtest(snap, TODAY, "now")
    feb = next(m for m in out["months"] if m["month"] == "2026-02")  # type: ignore[attr-defined]
    assert feb["actual"] == "100.00"


def test_backtest_without_full_months_has_nothing_to_compare(conn: sqlite3.Connection) -> None:
    out = year.backtest(Snapshot(conn), date(2026, 1, 10), "2026-01-10T08:00:00+01:00")
    assert out["months"] == [] and out["error_pct"] is None


@pytest.mark.asyncio
async def test_status_year_eval_button(service: Service) -> None:
    async with _client(service) as client:
        assert "Prognoza roczna — pomiar" in (await client.get("/status")).text
        await client.post("/status/year-eval")
        page = (await client.get("/status")).text
    assert "Pomiar prognozy rocznej: brak pełnych miesięcy do porównania" in page
    saved = db.kv_get(service.conn, year.BACKTEST_KEY)
    assert saved["error_pct"] is None and saved["history_months"] == 0


def test_unseried_lists_seasonal_payments_without_a_series(conn: sqlite3.Connection) -> None:
    seeded(conn)
    spend(conn, "400.00", "2026-06", "ubezpieczenia")
    rows = year.unseried(Snapshot(conn), TODAY)
    assert [(r.name, r.day, r.amount, r.count) for r in rows] == [
        ("ODBIORCA ubezpieczenia", date(2026, 6, 7), D("400.00"), 2)  # ostatnia z dwóch płatności
    ]
    serie(conn, "ubezpieczenia", "600.00", cadence="Y")
    assert year.unseried(Snapshot(conn), TODAY) == []


def test_save_settings_roundtrip_and_reset(conn: sqlite3.Connection) -> None:
    assert year.settings(conn) == (None, D(0))
    year.save_settings(conn, "2\xa0500,50", "1000")
    assert year.settings(conn) == (D("2500.50"), D("1000.00"))
    year.save_settings(conn, "300", "0")  # cel 0 = domyślny, nie zapisuje się
    assert year.settings(conn) == (D("300.00"), D(0))
    year.save_settings(conn, "", "")  # wróć do automatycznej i celu 0
    assert year.settings(conn) == (None, D(0))


@pytest.mark.parametrize(("flex_text", "target"), [("abc", ""), ("-5", ""), ("", "x"), ("", "-1")])
def test_save_settings_rejects_bad_values(
    conn: sqlite3.Connection, flex_text: str, target: str
) -> None:
    with pytest.raises(year.YearError):
        year.save_settings(conn, flex_text, target)
    assert year.settings(conn) == (None, D(0))


def test_memo_recomputes_after_a_write_and_on_new_day(conn: sqlite3.Connection) -> None:
    snap, memo = seeded(conn), year.Memo()
    first = memo.get(snap, TODAY, D(0))
    assert first is not None and memo.get(snap, TODAY, D(0)) is first
    db.kv_set(conn, year.FLEX_KEY, "250")
    assert memo.get(snap, TODAY, D(0)) is not first
    again = memo.get(snap, TODAY, D(0))
    assert memo.get(snap, date(2026, 10, 15), D(0)) is not again


@pytest.mark.asyncio
async def test_year_page_renders_and_saves_settings(service: Service) -> None:
    async with _client(service) as client:
        empty = (await client.get("/year")).text
        assert "potrzebuje salda rachunku PLN" in empty
        service.conn.execute(
            "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', ?)",
            ("2026-10-14T08:00:00+02:00",),
        )
        balance(service.conn)
        page = (await client.get("/year")).text
        assert "Saldo na koniec" in page and "Mogę wydać" in page and "<svg" in page
        res = await client.post("/year/settings", data={"flex": "abc", "target": ""})
        assert res.status_code in (200, 303)
    assert year.settings(service.conn) == (None, D(0))
    async with _client(service) as client:
        await client.post("/year/settings", data={"flex": "1200", "target": "500"})
    assert year.settings(service.conn) == (D("1200.00"), D("500.00"))
