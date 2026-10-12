"""Notowania WIBOR 3M z bankier.pl (M9 E4).

Bank zmienia oprocentowanie kredytu co 3 miesiące w dniu zmiany, ale stawkę bierze z notowania
sprzed kilku dni roboczych (`FIXING_LAG`; skalibrowane: dla zmiany 9.09.2026 bank użył 3,80%, tyle
co notowania z 3–4.09, a nie 3,83% z 9.09). Add-on raz dziennie czyta ostatnie notowanie i zapisuje
je w `kv`; dla dnia ustalenia stawki, którego nie ma jeszcze w zapisie, dociąga notowanie z daty.
Prognozy i powiadomienia budują `loan_sim`, `inbox` i `summary`; tu jest tylko odczyt, stan i daty.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import Awaitable, Callable, Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx

from budget.storage import db

log = logging.getLogger(__name__)

URL = "https://www.bankier.pl/mieszkaniowe/stopy-procentowe/wibor"
KEY = "wibor"
FIXING_LAG = 3  # dni robocze między notowaniem a dniem zmiany oprocentowania
KEEP = 120  # tyle ostatnich notowań w zapisie
ERROR_ALERT_DAYS = 3  # tyle dni nieudanych odczytów → karta w dzwonku
LOOKBACK = 5  # dni wstecz szukania notowania, gdy dzień jest świętem
_DAY = re.compile(r"<td>Data</td>\s*<td[^>]*>(\d{4}-\d{2}-\d{2})</td>")
_RATE = re.compile(r"rateChartType=3m\">WIBOR 3M</a></td>\s*<td[^>]*>\s*(-?\d+,\d+)%")

Fetch = Callable[[date | None], Awaitable[tuple[date, Decimal]]]


class WibError(ValueError):
    pass


def parse(html: str) -> tuple[date, Decimal]:
    """Dzień notowania i WIBOR 3M (%) ze strony; `WibError`, gdy układ strony się zmienił."""
    day, rate = _DAY.search(html), _RATE.search(html)
    if day is None or rate is None:
        raise WibError("Nie znaleziono WIBOR 3M na stronie notowań")
    return date.fromisoformat(day.group(1)), Decimal(rate.group(1).replace(",", "."))


def fixing_day(reset: date) -> date:
    """Dzień notowania, z którego bank bierze stawkę zmiany oprocentowania w dniu `reset`."""
    d, left = reset, FIXING_LAG
    while left:
        d -= timedelta(days=1)
        left -= d.weekday() < 5
    return d


async def fetch(day: date | None = None) -> tuple[date, Decimal]:
    """Ostatnie notowanie (`day` None) albo notowanie z `day`; w święto cofa się do poprzedniego."""
    async with httpx.AsyncClient(
        timeout=20, headers={"User-Agent": "ha-budget-app"}, follow_redirects=True
    ) as client:
        for back in range(LOOKBACK if day else 1):
            want = day - timedelta(days=back) if day else None
            resp = await client.get(URL, params={"rateDate": want.isoformat()} if want else None)
            resp.raise_for_status()
            try:
                return parse(resp.text)
            except WibError:
                if want is None:
                    raise
    raise WibError(f"Brak notowania WIBOR 3M w {LOOKBACK} dni do {day}")


def _raw(conn: sqlite3.Connection) -> dict[str, object]:
    return db.kv_get(conn, KEY) or {}


def quotes(conn: sqlite3.Connection) -> dict[date, Decimal]:
    """Zapisane notowania: dzień → WIBOR 3M (%)."""
    raw = _raw(conn).get("quotes")
    items = raw.items() if isinstance(raw, dict) else ()
    return {date.fromisoformat(k): Decimal(str(v)) for k, v in items}


def at(conn: sqlite3.Connection, day: date) -> tuple[date, Decimal] | None:
    """Ostatnie zapisane notowanie z dnia `day` albo wcześniejsze (None: brak)."""
    known = [(d, v) for d, v in quotes(conn).items() if d <= day]
    return max(known, default=None)


def error(conn: sqlite3.Connection) -> tuple[str, datetime] | None:
    """Ostatni błąd odczytu i od kiedy trwa (None: odczyt działa)."""
    raw = _raw(conn)
    if not raw.get("error") or not raw.get("error_since"):
        return None
    return str(raw["error"]), datetime.fromisoformat(str(raw["error_since"]))


async def refresh(
    conn: sqlite3.Connection,
    now: datetime,
    wanted: Iterable[date] = (),
    get: Fetch = fetch,
) -> None:
    """Jeden odczyt; nigdy nie rzuca (błąd trafia do stanu i dzwonka). Dla każdego dnia z `wanted`
    (dni ustalenia stawki), do którego nie ma jeszcze notowania, dociąga notowanie z tej daty."""
    raw = _raw(conn)
    known = quotes(conn)
    raw["checked"] = now.isoformat()
    try:
        latest, value = await get(None)
        known[latest] = value
        for day in wanted:
            if day <= latest and not any(day - timedelta(days=LOOKBACK) < d <= day for d in known):
                found, value = await get(day)
                known[found] = value
        raw.update(error=None, error_since=None)
    except Exception as exc:  # sieć, zmiana układu strony — wszystko ma być widoczne w panelu
        log.warning("Odczyt WIBOR nieudany: %s", exc)
        raw["error"] = f"{type(exc).__name__}: {exc}"[:200]
        if not raw.get("error_since"):
            raw["error_since"] = now.isoformat()
    raw["quotes"] = {d.isoformat(): str(v) for d, v in sorted(known.items())[-KEEP:]}
    db.kv_set(conn, KEY, raw)
