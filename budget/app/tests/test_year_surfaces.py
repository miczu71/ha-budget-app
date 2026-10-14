"""Prognoza roczna na powierzchniach (M18 E3): encja MQTT, źródło czatu, kafelek strony głównej."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

import httpx

from budget import ha_publisher, year, year_events
from budget.ask import sources
from budget.money import pl
from budget.snapshot import Snapshot

from .test_ask_sources import conn
from .test_web import client, service
from .test_year import TODAY, seeded

__all__ = ["client", "conn", "service"]

D = Decimal
NOW = datetime(2026, 10, 14, 12, 0)


def test_year_entity_matches_projection(conn: sqlite3.Connection) -> None:
    proj = year.build(seeded(conn), TODAY)
    assert proj is not None
    (ent,) = ha_publisher.year_entities(proj)
    assert ent.key == "year_end" and ent.state == f"{proj.end:.2f}"
    assert ent.attributes["horizon_end"] == "2026-12"
    assert ent.attributes["scenario_end"] is None


def test_year_entity_has_scenario_and_deficit(conn: sqlite3.Connection) -> None:
    snap = seeded(conn)
    year_events.add(
        conn,
        kind="one_off",
        mode="scenario",
        name="Premia",
        amount=D("4000"),
        start=date(2026, 12, 1),
    )
    year_events.add(
        conn,
        kind="one_off",
        mode="plan",
        name="Remont",
        amount=D("-999999"),
        start=date(2026, 11, 1),
    )
    proj = year.build(snap, TODAY)
    assert proj is not None
    (ent,) = ha_publisher.year_entities(proj)
    assert ent.attributes["first_deficit"] == "2026-11"
    assert ent.attributes["scenario_end"] == f"{proj.scenario.end:.2f}"  # type: ignore[union-attr]


def test_year_entity_absent_without_balance() -> None:
    assert ha_publisher.year_entities(None) == []


def test_year_source_matches_screen_and_anonymizes_events(conn: sqlite3.Connection) -> None:
    snap = seeded(conn)
    year_events.add(
        conn,
        kind="one_off",
        mode="plan",
        name="Remont u Kowalskich",
        amount=D("-500"),
        start=date(2026, 11, 1),
    )
    proj = year.build(snap, TODAY)
    assert proj is not None
    res = sources.run("year", sources.Ctx(conn, snap, TODAY, NOW, date(2026, 10, 1)))
    facts = {f.label: f.value for f in res.facts}
    assert facts["Saldo na koniec horyzontu"] == pl(proj.end, "PLN")
    llm = res.for_llm()
    assert "Kowalskich" not in str(llm) and "[Seria 1]" in str(llm)
    assert res.labels["[Seria 1]"] == "Remont u Kowalskich"


def test_year_source_without_balance_has_note() -> None:
    from budget.storage import db

    c = db.connect(":memory:")
    res = sources.run("year", sources.Ctx(c, Snapshot(c), TODAY, NOW, date(2026, 10, 1)))
    assert res.note and not res.facts


async def test_home_has_year_tile(client: httpx.AsyncClient) -> None:
    page = (await client.get("/")).text
    assert "Prognoza roczna »" in page and '/year"' in page


def test_year_source_event_fact_says_direction_and_span(conn: sqlite3.Connection) -> None:
    snap = seeded(conn)
    year_events.add(
        conn,
        kind="new_series",
        mode="plan",
        name="Czynsz",
        amount=D("500"),
        start=date(2026, 11, 1),
        direction="out",
    )
    res = sources.run("year", sources.Ctx(conn, snap, TODAY, NOW, date(2026, 10, 1)))
    value = next(f.value for f in res.facts if f.label == "Czynsz")
    assert "wydatek" in value and "od listopad 2026" in value
