"""Zdarzenia prognozy rocznej (M18 E2): CRUD, zastosowanie do projekcji i propozycje z historii."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget import forecast, year, year_events
from budget.categorize import engine
from budget.categorize.rules import Conditions, TextCondition
from budget.recurring import schedule as sch
from budget.recurring import series as S
from budget.service import Service
from budget.snapshot import Snapshot
from budget.storage import db

from .test_categorize_engine import conn
from .test_flex import months, pay, serie
from .test_web import _client, service
from .test_year import TODAY, balance, due, seeded

__all__ = ["conn", "service"]

D = Decimal
OCT, NOV, DEC = date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1)


def ev(
    kind: str, amount: str, start: date, end: date | None = None, **kw: object
) -> year_events.Event:
    base: dict[str, object] = {"id": 1, "mode": "plan", "source": "manual", "name": "Zdarzenie"}
    base.update(kw)
    return year_events.Event(kind=kind, amount=D(amount), start=start, end=end, **base)  # type: ignore[arg-type]


# --- apply ---------------------------------------------------------------------------------


def test_series_amount_changes_only_that_series_in_range() -> None:
    dues = {m: [due(1, m, "100", "in"), due(2, m, "50", "out")] for m in (OCT, NOV, DEC)}
    out, extra = year_events.apply(
        [ev("series_amount", "80", NOV, NOV, series_id=1)], dues, [OCT, NOV, DEC]
    )
    amounts = {m: [d.series.expected_amount for d in rows] for m, rows in out.items()}
    assert amounts[OCT] == [D("100"), D("50")]
    assert amounts[NOV] == [D("80"), D("50")]
    assert amounts[DEC] == [D("100"), D("50")]
    assert extra == {}
    assert dues[NOV][0].series.expected_amount == D("100")  # wejście bez zmian


def test_series_amount_open_ended_and_later_event_wins() -> None:
    dues = {m: [due(1, m, "100", "in")] for m in (OCT, NOV, DEC)}
    out, _ = year_events.apply(
        [
            ev("series_amount", "80", NOV, series_id=1, id=1),
            ev("series_amount", "60", DEC, series_id=1, id=2),
        ],
        dues,
        [OCT, NOV, DEC],
    )
    assert [out[m][0].series.expected_amount for m in (OCT, NOV, DEC)] == [
        D("100"),
        D("80"),
        D("60"),
    ]


def test_new_series_signs_by_direction_within_range() -> None:
    _, extra = year_events.apply(
        [
            ev("new_series", "300", NOV, DEC, direction="out"),
            ev("new_series", "50", OCT, OCT, direction="in", id=2),
        ],
        {},
        [OCT, NOV, DEC],
    )
    assert extra == {OCT: D("50"), NOV: D("-300"), DEC: D("-300")}


def test_one_off_hits_a_single_month_and_keeps_sign() -> None:
    _, extra = year_events.apply(
        [ev("one_off", "-1200", NOV, NOV), ev("one_off", "500", NOV, NOV, id=2)],
        {},
        [OCT, NOV, DEC],
    )
    assert extra == {NOV: D("-700")}


def test_events_outside_horizon_are_ignored() -> None:
    _, extra = year_events.apply(
        [ev("one_off", "100", date(2027, 5, 1), date(2027, 5, 1))], {}, [OCT, NOV]
    )
    assert extra == {}


# --- project / build -----------------------------------------------------------------------


def test_project_adds_event_amounts_to_balance_and_buffer_limit() -> None:
    p = year.project(
        start_balance=D("1000"),
        today=TODAY,
        dues={},
        flex=D(0),
        irregular=D(0),
        seasonal={},
        buffer=D(0),
        target=D(0),
        extra={NOV: D("-400")},
    )
    assert [m.balance for m in p.months] == [D("1000"), D("600"), D("600")]
    assert p.months[1].events == D("-400") and p.months[1].net == D("-400")
    assert p.end == D("600")


def test_build_plan_changes_base_and_scenario_adds_second_line(conn: sqlite3.Connection) -> None:
    snap = seeded(conn)
    base = year.build(snap, TODAY)
    assert base is not None and base.scenario is None and base.scenario_delta is None
    year_events.add(conn, kind="one_off", mode="plan", name="Remont", amount=D("-1000"), start=NOV)
    year_events.add(
        conn, kind="one_off", mode="scenario", name="Premia", amount=D("4000"), start=DEC
    )
    p = year.build(snap, TODAY)
    assert p is not None and p.scenario is not None
    assert p.end == base.end - 1000
    assert p.scenario.end == p.end + 4000 and p.scenario_delta == D("4000")
    assert p.scenario.start_balance == p.start_balance  # druga linia startuje z tego samego salda
    assert p.scenario.months[0].events == 0 and p.months[2].events == 0
    assert p.scenario.months[2].events == D("4000")


def test_dismissed_events_do_not_count(conn: sqlite3.Connection) -> None:
    snap = seeded(conn)
    year_events.add(
        conn,
        kind="one_off",
        mode="plan",
        name="X",
        amount=D("-1000"),
        start=NOV,
        status="dismissed",
    )
    p = year.build(snap, TODAY)
    base = year.build(Snapshot(conn), TODAY)
    assert p is not None and base is not None and p.end == base.end and p.scenario is None


# --- CRUD i walidacja ----------------------------------------------------------------------


def test_add_validates(conn: sqlite3.Connection) -> None:
    sid = serie(conn, "a", "100")
    with pytest.raises(year_events.YearEventError, match="nazwę"):
        year_events.add(conn, kind="one_off", mode="plan", name=" ", amount=D(5), start=NOV)
    with pytest.raises(year_events.YearEventError, match="zerem"):
        year_events.add(conn, kind="one_off", mode="plan", name="X", amount=D(0), start=NOV)
    with pytest.raises(year_events.YearEventError, match="dodatnia"):
        year_events.add(
            conn, kind="new_series", mode="plan", name="X", amount=D(-5), start=NOV, direction="out"
        )
    with pytest.raises(year_events.YearEventError, match="kierunek"):
        year_events.add(conn, kind="new_series", mode="plan", name="X", amount=D(5), start=NOV)
    with pytest.raises(year_events.YearEventError, match="serię"):
        year_events.add(
            conn, kind="series_amount", mode="plan", name="X", amount=D(5), start=NOV, series_id=999
        )
    with pytest.raises(year_events.YearEventError, match="przed początkiem"):
        year_events.add(
            conn,
            kind="new_series",
            mode="plan",
            name="X",
            amount=D(5),
            start=DEC,
            end=NOV,
            direction="in",
        )
    with pytest.raises(year_events.YearEventError, match="tryb"):
        year_events.add(conn, kind="one_off", mode="inny", name="X", amount=D(5), start=NOV)
    year_events.add(
        conn,
        kind="series_amount",
        mode="plan",
        name="X",
        amount=D(5),
        start=date(2026, 11, 17),
        series_id=sid,
    )
    assert year_events.active(conn)[0].start == NOV  # data → początek miesiąca


def test_update_and_delete(conn: sqlite3.Connection) -> None:
    i = year_events.add(conn, kind="one_off", mode="plan", name="A", amount=D(-10), start=NOV)
    year_events.update(conn, i, mode="scenario", name="B", amount=D(-20), start=DEC, end=None)
    e = year_events.get(conn, i)
    assert (e.mode, e.name, e.amount, e.start, e.end) == ("scenario", "B", D("-20"), DEC, DEC)
    year_events.delete(conn, i)
    assert year_events.active(conn) == []
    with pytest.raises(year_events.YearEventError):
        year_events.get(conn, i)


# --- propozycje ----------------------------------------------------------------------------


def payday(conn: sqlite3.Connection, expected: str) -> int:
    cond = Conditions(
        text=(TextCondition("counterparty_name", "equals", "FIRMA X"),), direction="in"
    )
    sid = S.insert(
        conn, name="Wypłata", direction="in", cadence="M", conditions=cond,
        expected=D(expected), tolerance=D("5"), anchor_day=24, status="active", origin="manual",
        key=None,
    )  # fmt: skip
    db.kv_set(conn, forecast.PAYDAY_KEY, sid)
    return sid


def pay_year(conn: sqlite3.Connection, year_: int, amounts: list[str]) -> None:
    for m, a in zip(months(f"{year_}-01", len(amounts)), amounts, strict=True):
        pay(conn, a, m)
    engine.recategorize(conn)


def test_pit_proposal_from_last_year_drop(conn: sqlite3.Connection) -> None:
    sid = payday(conn, "10000")
    pay_year(conn, 2025, ["10000"] * 3 + ["8000"] * 9)
    today = date(2026, 3, 5)
    props = year_events.proposals(Snapshot(conn), today)
    pit = [p for p in props if p.key.startswith("pit:")]
    assert [(p.key, p.amount, p.start, p.end, p.series_id) for p in pit] == [
        (f"pit:{sid}:2026:b", D("8000.00"), date(2026, 4, 1), date(2026, 12, 1), sid)
    ]  # styczeń–marzec = kwota bieżąca serii (10000), więc „a” pomijamy
    assert pit[0].mode == "plan" and pit[0].kind == "series_amount"


def test_pit_proposal_restores_amount_next_january(conn: sqlite3.Connection) -> None:
    sid = payday(conn, "8000")
    pay_year(conn, 2026, ["10000"] * 3 + ["8000"] * 7)  # do października 2026
    props = year_events.proposals(Snapshot(conn), date(2026, 11, 10))
    pit = [p for p in props if p.key.startswith("pit:")]
    assert [(p.key, p.amount, p.start, p.end) for p in pit] == [
        (f"pit:{sid}:2027:a", D("10000.00"), date(2027, 1, 1), date(2027, 3, 1))
    ]
    e = ev("series_amount", "10000", pit[0].start, pit[0].end, series_id=sid)
    dues = {date(2027, 2, 1): [sch.Due(S.all_series(conn)[0], date(2027, 2, 24), sch.EXPECTED)]}
    out, _ = year_events.apply([e], dues, [date(2027, 2, 1)])
    assert out[date(2027, 2, 1)][0].series.expected_amount == D("10000.00")


def test_pit_needs_payday_series_and_a_real_drop(conn: sqlite3.Connection) -> None:
    pay_year(conn, 2025, ["10000"] * 3 + ["8000"] * 9)
    assert year_events.proposals(Snapshot(conn), date(2026, 3, 5)) == []  # brak serii wypłaty
    payday(conn, "10000")
    pay_year(
        conn, 2024, ["10000"] * 12
    )  # zwykły rok bez spadku nie jest tematem (rok docelowy 2025)
    assert [p.key for p in year_events.proposals(Snapshot(conn), date(2025, 3, 5))] == []


def test_bonus_proposal_is_scenario_in_same_month(conn: sqlite3.Connection) -> None:
    for m, a in zip(months("2025-01", 12), ["5000"] * 5 + ["12000"] + ["5000"] * 6, strict=True):
        pay(conn, a, m)
    engine.recategorize(conn)
    props = year_events.proposals(Snapshot(conn), date(2026, 3, 5))
    bonus = [p for p in props if p.key.startswith("bonus:")]
    assert [(p.kind, p.mode, p.amount, p.start, p.end) for p in bonus] == [
        ("one_off", "scenario", D("7000.00"), date(2026, 6, 1), date(2026, 6, 1))
    ]
    assert "Firma X" in bonus[0].name  # nazwa źródła tylko w bazie użytkownika


def test_past_months_are_not_proposed(conn: sqlite3.Connection) -> None:
    for m, a in zip(months("2025-01", 12), ["5000"] * 2 + ["12000"] + ["5000"] * 9, strict=True):
        pay(conn, a, m)
    engine.recategorize(conn)
    assert year_events.proposals(Snapshot(conn), date(2026, 10, 14)) == []  # marzec 2026 już minął


def test_decided_proposals_do_not_return(conn: sqlite3.Connection) -> None:
    for m, a in zip(months("2025-01", 12), ["5000"] * 5 + ["12000"] + ["5000"] * 6, strict=True):
        pay(conn, a, m)
    engine.recategorize(conn)
    snap, today = Snapshot(conn), date(2026, 3, 5)
    [p] = year_events.proposals(snap, today)
    year_events.decide(conn, p, approve=False)
    assert year_events.proposals(snap, today) == [] and year_events.active(conn) == []
    # zatwierdzenie: zdarzenie aktywne z kluczem; usunięcie odrzuca, więc nie wraca
    conn.execute("DELETE FROM year_event")
    year_events.decide(conn, p, approve=True)
    [e] = year_events.active(conn)
    assert (e.source, e.mode, e.amount, e.key) == ("proposed", "scenario", p.amount, p.key)
    assert year_events.proposals(snap, today) == []
    year_events.delete(conn, e.id)
    assert year_events.active(conn) == [] and year_events.proposals(snap, today) == []


# --- formularz i ekran ---------------------------------------------------------------------


def test_save_form_signs_one_off_and_edits(conn: sqlite3.Connection) -> None:
    form = {"kind": "one_off", "mode": "plan", "name": "Remont", "amount": "1 200,50",
            "direction": "out", "start": "2026-11", "end": "", "series_id": ""}  # fmt: skip
    year_events.save_form(conn, None, form)
    [e] = year_events.active(conn)
    assert (e.amount, e.start, e.end) == (D("-1200.50"), NOV, NOV)
    year_events.save_form(conn, e.id, {**form, "direction": "in", "amount": "300"})
    assert year_events.get(conn, e.id).amount == D("300.00")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("amount", "abc", "kwotę"),
        ("amount", "-5", "kwotę"),
        ("start", "", "początku"),
        ("start", "11.2026", "RRRR-MM"),
    ],
)
def test_save_form_rejects_bad_input(
    conn: sqlite3.Connection, field: str, value: str, message: str
) -> None:
    form = {"kind": "one_off", "mode": "plan", "name": "X", "amount": "10", "direction": "out",
            "start": "2026-11", "end": "", "series_id": ""}  # fmt: skip
    with pytest.raises(year_events.YearEventError, match=message):
        year_events.save_form(conn, None, {**form, field: value})
    assert year_events.active(conn) == []


@pytest.mark.asyncio
async def test_year_page_events_flow(service: Service) -> None:
    c = service.conn
    c.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', ?)",
        ("2026-10-14T08:00:00+02:00",),
    )
    balance(c)
    form = {"kind": "one_off", "mode": "scenario", "name": "Premia testowa", "amount": "4000",
            "direction": "in", "start": "2026-12"}  # fmt: skip
    async with _client(service) as client:
        assert "Brak zdarzeń" in (await client.get("/year")).text
        await client.post("/year/events", data=form)
        page = (await client.get("/year")).text
        assert "Premia testowa" in page and "Scenariusz: koniec" in page and "fc-scenario" in page
        [e] = year_events.active(c)
        await client.post(f"/year/events/{e.id}", data={**form, "name": "Premia zmieniona"})
        assert year_events.get(c, e.id).name == "Premia zmieniona"
        bad = await client.post("/year/events", data={**form, "amount": "x"})
        assert bad.status_code in (200, 303) and len(year_events.active(c)) == 1
        await client.post(f"/year/events/{e.id}/delete")
    assert year_events.active(c) == []
