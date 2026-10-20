"""Akcje pracownicze (M11): odczyt encji HA do `kv`; `networth.compute` czyta tylko `kv`."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from budget.ha_client import HAClient
from budget.storage import db

log = logging.getLogger(__name__)

KEY = "stocks_nokia"
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
