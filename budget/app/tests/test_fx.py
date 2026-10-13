"""Kursy średnie NBP (tabela A): parser, kurs dla dnia transakcji, dociąganie (M23 E1)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from budget import fx

from .test_categorize_engine import add, conn

__all__ = ["conn"]

BODY = {
    "table": "A",
    "code": "EUR",
    "rates": [
        {"no": "172/A/NBP/2026", "effectiveDate": "2026-09-04", "mid": 4.2523},
        {"no": "173/A/NBP/2026", "effectiveDate": "2026-09-07", "mid": 4.2611},
    ],
}


def test_parse_reads_effective_dates_and_mids() -> None:
    assert fx.parse(BODY) == {
        date(2026, 9, 4): Decimal("4.2523"),
        date(2026, 9, 7): Decimal("4.2611"),
    }


def test_spans_split_ranges_longer_than_nbp_limit() -> None:
    assert fx.spans(date(2026, 1, 1), date(2026, 1, 10)) == [(date(2026, 1, 1), date(2026, 1, 10))]
    long = fx.spans(date(2026, 1, 1), date(2026, 6, 30))
    assert long[0] == (date(2026, 1, 1), date(2026, 4, 3))  # 93 dni włącznie
    assert long[-1][1] == date(2026, 6, 30)
    assert all(b >= a for a, b in long)


def test_rate_uses_last_table_before_transaction_day(conn: sqlite3.Connection) -> None:
    fx.store(conn, "EUR", fx.parse(BODY))
    # pn 7.09: tabela z pt 4.09 (kurs z dnia roboczego poprzedzającego), nie z tego samego dnia
    assert fx.rate(conn, "EUR", date(2026, 9, 7)) == (date(2026, 9, 4), Decimal("4.2523"))
    assert fx.rate(conn, "EUR", date(2026, 9, 8)) == (date(2026, 9, 7), Decimal("4.2611"))
    assert fx.rate(conn, "EUR", date(2026, 9, 4)) is None  # brak wcześniejszej tabeli
    assert fx.rate(conn, "EUR", date(2026, 9, 30)) is None  # luka dłuższa niż LOOKBACK
    assert fx.rate(conn, "CZK", date(2026, 9, 8)) is None


def recorder(
    table: dict[str, dict[date, Decimal]],
) -> tuple[fx.Fetch, list[tuple[str, date, date]]]:
    calls: list[tuple[str, date, date]] = []

    async def get(cur: str, start: date, end: date) -> dict[date, Decimal]:
        calls.append((cur, start, end))
        return {d: v for d, v in table.get(cur, {}).items() if start <= d <= end}

    return get, calls


async def test_refresh_fetches_only_missing_days_of_fx_transactions(
    conn: sqlite3.Connection,
) -> None:
    add(conn, "-100.00", day="2026-09-08", account=2, orig_amount="-23.45", orig_currency="EUR")
    add(conn, "-10.00", day="2026-09-08", account=2)  # PLN — bez kursu
    get, calls = recorder({"EUR": fx.parse(BODY)})
    await fx.refresh(conn, get)
    assert calls == [("EUR", date(2026, 8, 29), date(2026, 9, 7))]
    assert fx.rate(conn, "EUR", date(2026, 9, 8)) == (date(2026, 9, 7), Decimal("4.2611"))
    await fx.refresh(conn, get)
    assert len(calls) == 1  # kurs już jest — bez zapytania


async def test_refresh_never_raises(conn: sqlite3.Connection) -> None:
    add(conn, "-100.00", day="2026-09-08", account=2, orig_amount="-23.45", orig_currency="EUR")

    async def boom(cur: str, start: date, end: date) -> dict[date, Decimal]:
        raise OSError("sieć")

    await fx.refresh(conn, boom)
    assert fx.rate(conn, "EUR", date(2026, 9, 8)) is None
