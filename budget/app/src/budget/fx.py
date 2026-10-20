"""Kurs średni NBP, tabela A (M26 E1) — wycena salda walutowego (EUR) w majątku netto.

Odzyskane z wycofanego M23 (82ce0ff^), okrojone o część dla transakcji kartą. Kursy zapisane w
`fx_rate` (migracja 020); API zwraca najwyżej `MAX_SPAN` dni na zapytanie.
"""

from __future__ import annotations

import bisect
import logging
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import httpx

log = logging.getLogger(__name__)

URL = "https://api.nbp.pl/api/exchangerates/rates/A/{cur}/{start}/{end}/"
MAX_SPAN = 93  # dni w jednym zapytaniu (limit NBP)
LOOKBACK = 10  # dni wstecz szukania tabeli (weekend + święta)
FRESH_DAYS = 4  # starsza tabela niż tyle dni = dociągnij nowe

Fetch = Callable[[str, date, date], Awaitable[dict[date, Decimal]]]


def parse(body: dict[str, Any]) -> dict[date, Decimal]:
    """Dzień tabeli → kurs średni z odpowiedzi NBP."""
    return {date.fromisoformat(r["effectiveDate"]): Decimal(str(r["mid"])) for r in body["rates"]}


def spans(start: date, end: date) -> list[tuple[date, date]]:
    """Zakres podzielony na kawałki po najwyżej `MAX_SPAN` dni (włącznie)."""
    out = []
    while start <= end:
        stop = min(start + timedelta(days=MAX_SPAN - 1), end)
        out.append((start, stop))
        start = stop + timedelta(days=1)
    return out


async def fetch(cur: str, start: date, end: date) -> dict[date, Decimal]:
    """Kursy z zakresu; pusty wynik, gdy NBP nie ma w nim tabel (404 „Brak danych”)."""
    out: dict[date, Decimal] = {}
    async with httpx.AsyncClient(timeout=20, headers={"Accept": "application/json"}) as client:
        for a, b in spans(start, end):
            resp = await client.get(URL.format(cur=cur.lower(), start=a, end=b))
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            out |= parse(resp.json())
    return out


def store(conn: sqlite3.Connection, cur: str, rates: dict[date, Decimal]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO fx_rate (currency, day, mid) VALUES (?, ?, ?)",
        [(cur, d.isoformat(), str(v)) for d, v in rates.items()],
    )


class Rates:
    """Zapisane kursy wczytane raz; `get` = tabela z ostatniego dnia przed `day`."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._days: dict[str, list[date]] = {}
        self._mids: dict[str, list[Decimal]] = {}
        for cur, day, mid in conn.execute("SELECT currency, day, mid FROM fx_rate ORDER BY day"):
            self._days.setdefault(cur, []).append(date.fromisoformat(day))
            self._mids.setdefault(cur, []).append(Decimal(mid))

    def at(self, cur: str, day: date) -> tuple[date, Decimal] | None:
        """Tabela z `day` albo ostatnia wcześniejsza (wycena salda na koniec dnia): (dzień tabeli,
        kurs); None bez tabeli w `LOOKBACK` dniach."""
        days = self._days.get(cur, [])
        i = bisect.bisect_right(days, day) - 1
        if i < 0 or days[i] < day - timedelta(days=LOOKBACK):
            return None
        return days[i], self._mids[cur][i]

    def get(self, cur: str, day: date) -> Decimal | None:
        """None: brak tabeli w `LOOKBACK` dniach przed `day`."""
        days = self._days.get(cur, [])
        i = bisect.bisect_left(days, day) - 1
        if i < 0 or days[i] < day - timedelta(days=LOOKBACK):
            return None
        return self._mids[cur][i]


async def refresh(
    conn: sqlite3.Connection, day: date, get: Fetch | None = None, since: date | None = None
) -> None:
    """Dociąga kursy walut kont potrzebne do wyceny na `day` (od `since`, domyślnie `LOOKBACK` dni
    wstecz), gdy ostatnia tabela jest starsza niż `FRESH_DAYS`. Nigdy nie rzuca — brak kursu
    oznacza tylko pozycję bez wyceny w majątku."""
    try:
        rates = Rates(conn)
        currencies = [
            r[0]
            for r in conn.execute("SELECT DISTINCT currency FROM account WHERE currency != 'PLN'")
        ]
    except Exception:
        log.exception("Kursy NBP: odczyt bazy nieudany")
        return
    for cur in sorted(currencies):
        found = rates.at(cur, day)
        if since is None and found and found[0] >= day - timedelta(days=FRESH_DAYS):
            continue
        try:
            store(
                conn, cur, await (get or fetch)(cur, since or day - timedelta(days=LOOKBACK), day)
            )
        except Exception as exc:  # sieć, NBP, baza
            log.warning("Kursy NBP %s nieudane: %s", cur, exc)


def covers(conn: sqlite3.Connection, since: date) -> bool:
    """Każda waluta kont ma zapisany kurs z `LOOKBACK` dni od `since` (wycena historii możliwa)."""
    for (cur,) in conn.execute("SELECT DISTINCT currency FROM account WHERE currency != 'PLN'"):
        stop = (since + timedelta(days=LOOKBACK)).isoformat()
        if not conn.execute(
            "SELECT 1 FROM fx_rate WHERE currency = ? AND day BETWEEN ? AND ?",
            (cur, since.isoformat(), stop),
        ).fetchone():
            return False
    return True
