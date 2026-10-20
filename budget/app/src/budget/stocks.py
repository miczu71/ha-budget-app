"""Akcje pracownicze (M11): odczyt encji HA do `kv`; `networth.compute` czyta tylko `kv`."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from budget.ha_client import HAClient, HAError
from budget.storage import db

log = logging.getLogger(__name__)

KEY = "stocks_nokia"
HISTORY_FLAG = "stocks_history_done"
HISTORY_FROM = date(2026, 7, 1)  # statystyki HA sięgają tylko lipca 2026 (E0)
GROUP = "inwestycje"  # = networth.INVESTMENTS (stocks nie importuje networth)
NAME_VALUE = "Akcje Nokia"
NAME_UNVESTED = "Akcje Nokia — niezawiązane"
_TZ = ZoneInfo("Europe/Warsaw")
_BAD = {"unavailable", "unknown", "none", ""}


@dataclass(frozen=True)
class Holding:
    market_value: Decimal
    unvested_qty: Decimal
    price: Decimal
    next_vest: date | None
    next_vest_qty: Decimal | None
    fetched_at: datetime


def _state(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    state = str(data.get("state", "")).strip()
    return None if state.lower() in _BAD else state


def _dec(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


async def refresh(conn: sqlite3.Connection, ha: HAClient, prefix: str, now: datetime) -> None:
    """Zapis stanu encji do `kv`; brak encji / `unavailable` zostawia poprzedni wpis."""
    if not prefix or not ha.available:
        return
    market = await ha.get_state(f"{prefix}market_value_pln")
    price = await ha.get_state(f"{prefix}price_pln")
    unvested = await ha.get_state(f"{prefix}unvested_qty")
    vest = await ha.get_state(f"{prefix}next_vest_date")
    mv, pr, uq = _dec(_state(market)), _dec(_state(price)), _dec(_state(unvested))
    if mv is None or pr is None or uq is None:
        log.warning("Akcje: encje %s* niedostępne — zostaje poprzedni wpis", prefix)
        return
    next_vest: date | None = None
    vest_state = _state(vest)
    if vest_state:
        try:
            next_vest = date.fromisoformat(vest_state[:10])
        except ValueError:
            next_vest = None
    qty_raw = (vest or {}).get("attributes", {}).get("next_vest_qty")
    qty = _dec(str(qty_raw)) if qty_raw is not None else None
    db.kv_set(
        conn,
        KEY,
        {
            "market_value": str(mv),
            "unvested_qty": str(uq),
            "price": str(pr),
            "next_vest": next_vest.isoformat() if next_vest else None,
            "next_vest_qty": str(qty) if qty is not None else None,
            "fetched_at": now.isoformat(),
        },
    )


def load(conn: sqlite3.Connection) -> Holding | None:
    raw = db.kv_get(conn, KEY)
    if not isinstance(raw, dict):
        return None
    try:
        return Holding(
            market_value=Decimal(raw["market_value"]),
            unvested_qty=Decimal(raw["unvested_qty"]),
            price=Decimal(raw["price"]),
            next_vest=date.fromisoformat(raw["next_vest"]) if raw.get("next_vest") else None,
            next_vest_qty=Decimal(raw["next_vest_qty"]) if raw.get("next_vest_qty") else None,
            fetched_at=datetime.fromisoformat(raw["fetched_at"]),
        )
    except (KeyError, ValueError, InvalidOperation):
        return None


def _bucket_value(rows: list[dict[str, Any]], year: int, month: int, *keys: str) -> Decimal | None:
    """Wartość kubełka miesiąca (`start` w ms → data lokalna); pierwszy dostępny z `keys`."""
    for row in rows:
        try:
            start = datetime.fromtimestamp(float(row["start"]) / 1000, _TZ)
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            continue
        if (start.year, start.month) != (year, month):
            continue
        for key in keys:
            raw = row.get(key)
            if raw is not None and (val := _dec(str(raw))) is not None:
                return val
        return None
    return None


async def backfill_history(conn: sqlite3.Connection, ha: HAClient, prefix: str, today: date) -> int:
    """Jednorazowo dopisuje składniki akcji do przybliżonych migawek z końców miesięcy od 07.2026.
    Błąd WS = brak zmian i brak flagi (ponowienie przy następnej migawce)."""
    if not prefix or not ha.available or db.kv_get(conn, HISTORY_FLAG):
        return 0
    month_first = today.replace(day=1)
    rows = conn.execute(
        "SELECT day, liabilities, components_json FROM networth_snapshot "
        "WHERE approx = 1 AND day >= ? AND day < ? ORDER BY day",
        (HISTORY_FROM.isoformat(), month_first.isoformat()),
    ).fetchall()
    if not rows:
        return 0
    ids = [f"{prefix}market_value_pln", f"{prefix}unvested_qty", f"{prefix}price_pln"]
    start = datetime(HISTORY_FROM.year, HISTORY_FROM.month, 1, tzinfo=_TZ)
    end = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=_TZ)
    try:
        stats = await ha.monthly_statistics(ids, start, end)
    except HAError as exc:
        log.warning(
            "Akcje: historia statystyk niedostępna (%s) — ponowię przy następnej migawce", exc
        )
        return 0
    done = 0
    for row in rows:
        day = date.fromisoformat(row["day"])
        comps = json.loads(row["components_json"])
        if any(c.get("name") == NAME_VALUE for c in comps):
            continue
        market = _bucket_value(stats.get(ids[0], []), day.year, day.month, "state")
        unvested = _bucket_value(stats.get(ids[1], []), day.year, day.month, "state", "mean")
        price = _bucket_value(stats.get(ids[2], []), day.year, day.month, "state")
        if market is None or unvested is None or price is None:
            continue
        value = (unvested * price).quantize(Decimal("0.01"))
        for name, amount in ((NAME_VALUE, market), (NAME_UNVESTED, value)):
            comps.append(
                {
                    "group": GROUP,
                    "name": name,
                    "amount": str(amount),
                    "liability": False,
                    "note": None,
                    "stale": False,
                }
            )
        assets = sum((Decimal(c["amount"]) for c in comps if not c["liability"]), Decimal(0))
        total = assets - Decimal(row["liabilities"])
        conn.execute(
            "UPDATE networth_snapshot SET total = ?, assets = ?, components_json = ? "
            "WHERE day = ? AND approx = 1",
            (str(total), str(assets), json.dumps(comps, ensure_ascii=False), row["day"]),
        )
        done += 1
    db.kv_set(conn, HISTORY_FLAG, True)
    return done
