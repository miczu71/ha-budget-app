"""Czat M12 E3b: rejestr źródeł danych — wartości jak na ekranie, do LLM bez nazw."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from budget import forecast
from budget.ask import sources
from budget.snapshot import Snapshot

from .test_categorize_engine import conn
from .test_forecast import at, seeded

__all__ = ["conn"]

TODAY = date(2026, 10, 3)


def ctx(c: sqlite3.Connection, now: datetime) -> sources.Ctx:
    return sources.Ctx(c, Snapshot(c), TODAY, now, date(2026, 10, 1))


def test_registry_names_are_unique_and_described() -> None:
    names = [s.name for s in sources.REGISTRY]
    assert len(names) == len(set(names)) and "transactions" not in names
    assert all(s.description and s.label for s in sources.REGISTRY)
    assert tuple(names) == sources.NAMES


def test_payday_matches_forecast(conn: sqlite3.Connection) -> None:
    seeded(conn)
    now = at(3)
    fc = forecast.for_today(Snapshot(conn), TODAY, now)
    assert fc is not None
    res = sources.run("payday", ctx(conn, now))
    facts = {f.label: f.value for f in res.facts}
    assert facts["Wolne środki dziś"].startswith("4")  # 5000 − dług karty 400 = 4 600
    assert res.link == "/"
    assert res.filters  # „jak policzono”
    assert "Wolne środki dziś" in str(res.for_llm())


def test_payday_without_balance_has_note(conn: sqlite3.Connection) -> None:
    res = sources.run("payday", ctx(conn, at(3)))
    assert not res.facts and "salda" in res.note.lower()


def test_unknown_source_is_rejected(conn: sqlite3.Connection) -> None:
    try:
        sources.run("nie_ma", ctx(conn, at(3)))
    except sources.SourceError as exc:
        assert "nie_ma" in str(exc)
    else:
        raise AssertionError("brak błędu")


def test_for_llm_replaces_private_names() -> None:
    res = sources.SourceResult(
        source="x",
        facts=[sources.Fact("Konto A", "10,00 zł", llm_label="[K1]")],
        filters=["jak policzono"],
        link="/",
    )
    assert "Konto A" not in str(res.for_llm()) and res.labels == {"[K1]": "Konto A"}


def test_month_parsing_defaults_to_current() -> None:
    assert sources.month_of("", date(2026, 10, 3)) == date(2026, 10, 1)
    assert sources.month_of("2026-08", date(2026, 10, 3)) == date(2026, 8, 1)
    assert sources.month_of("zły", date(2026, 10, 3)) == date(2026, 10, 1)
