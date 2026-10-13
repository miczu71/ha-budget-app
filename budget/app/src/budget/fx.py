"""Kursy średnie NBP, tabela A (M23 E1) — odniesienie do kosztu przewalutowania płatności kartą.

Dla transakcji z dnia D bierzemy tabelę z ostatniego dnia roboczego przed D (konwencja podatkowa;
tabela z dnia D ukazuje się w południe). Kursy dociągane z api.nbp.pl tylko dla dni transakcji
walutowych, których jeszcze nie pokrywa zapis; API zwraca najwyżej `MAX_SPAN` dni na zapytanie.
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

# Transakcja walutowa: kwotę w walucie zna tylko CSV karty (API jej nie podaje, M23 E0)
IS_FX = "orig_currency IS NOT NULL"

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

    def get(self, cur: str, day: date) -> Decimal | None:
        """None: brak tabeli w `LOOKBACK` dniach przed `day`."""
        days = self._days.get(cur, [])
        i = bisect.bisect_left(days, day) - 1
        if i < 0 or days[i] < day - timedelta(days=LOOKBACK):
            return None
        return self._mids[cur][i]


def _needed(conn: sqlite3.Connection) -> dict[str, set[date]]:
    out: dict[str, set[date]] = {}
    for cur, day in conn.execute(
        f"SELECT DISTINCT orig_currency, COALESCE(tx_date, booking_date) FROM txn WHERE {IS_FX}"
    ):
        out.setdefault(cur, set()).add(date.fromisoformat(day))
    return out


async def refresh(conn: sqlite3.Connection, get: Fetch = fetch) -> None:
    """Dociąga kursy brakujące dla dni transakcji walutowych; nigdy nie rzuca (woła ją pętla
    serwisu i import CSV — brak kursu oznacza tylko nieznany koszt)."""
    try:
        rates = Rates(conn)
        needed = _needed(conn)
    except Exception:
        log.exception("Kursy NBP: odczyt bazy nieudany")
        return
    for cur, days in sorted(needed.items()):
        missing = sorted(d for d in days if rates.get(cur, d) is None)
        if not missing:
            continue
        try:
            got = await get(
                cur, missing[0] - timedelta(days=LOOKBACK), missing[-1] - timedelta(days=1)
            )
            store(conn, cur, got)
        except Exception as exc:  # sieć, NBP, baza — koszt policzy się przy następnym odczycie
            log.warning("Kursy NBP %s nieudane: %s", cur, exc)
