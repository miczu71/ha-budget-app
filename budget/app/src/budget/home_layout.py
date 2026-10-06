"""Układ kafelków strony głównej (M16): kolejność i ukrywanie, wspólne dla wszystkich urządzeń."""

from __future__ import annotations

import sqlite3
from typing import NamedTuple

from budget.storage import db

KEY = "home_layout"

TILES: dict[str, str] = {  # domyślna kolejność
    "forecast": "Do wypłaty",
    "spending": "Gdzie poszły pieniądze",
    "inbox": "Do decyzji",
    "balance": "Bilans miesiąca",
    "card": "Karta kredytowa",
    "upcoming": "Co jeszcze zejdzie",
    "recent": "Ostatnie transakcje",
    "months": "Ostatnie 12 miesięcy",
}


class Tile(NamedTuple):
    key: str
    name: str
    hidden: bool


def load(conn: sqlite3.Connection) -> list[Tile]:
    """Zapisany układ; nieznane klucze odpadają, nowe kafelki trafiają na koniec jako widoczne."""
    saved = db.kv_get(conn, KEY) or {}
    order = [k for k in saved.get("order", []) if k in TILES]
    order += [k for k in TILES if k not in order]
    hidden = set(saved.get("hidden", []))
    return [Tile(k, TILES[k], k in hidden) for k in order]


def _save(conn: sqlite3.Connection, tiles: list[Tile]) -> None:
    db.kv_set(
        conn, KEY, {"order": [t.key for t in tiles], "hidden": [t.key for t in tiles if t.hidden]}
    )


def move(conn: sqlite3.Connection, key: str, delta: int) -> None:
    """Przesuwa kafelek o `delta` miejsc; na brzegu nic się nie dzieje."""
    tiles = load(conn)
    i = next(n for n, t in enumerate(tiles) if t.key == key)
    j = i + delta
    if 0 <= j < len(tiles):
        tiles[i], tiles[j] = tiles[j], tiles[i]
        _save(conn, tiles)


def toggle(conn: sqlite3.Connection, key: str) -> None:
    tiles = load(conn)
    _save(conn, [t._replace(hidden=not t.hidden) if t.key == key else t for t in tiles])


def reset(conn: sqlite3.Connection) -> None:
    db.kv_set(conn, KEY, None)
