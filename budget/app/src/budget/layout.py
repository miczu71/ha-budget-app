"""Układ listy pozycji (kolejność i ukrywanie) zapisany w bazie, wspólny dla wszystkich urządzeń.
Używany przez kafelki strony głównej (M16) i zakładki u góry (M28)."""

from __future__ import annotations

import sqlite3
from typing import NamedTuple

from budget.storage import db


class Item(NamedTuple):
    key: str
    name: str
    hidden: bool
    pinned: bool = False


class Layout:
    """`items` w domyślnej kolejności; `pinned` — klucze stale na początku, nieprzesuwalne
    i nieukrywalne."""

    def __init__(self, kv_key: str, items: dict[str, str], pinned: tuple[str, ...] = ()) -> None:
        self.kv_key = kv_key
        self.items = items
        self.pinned = pinned

    def load(self, conn: sqlite3.Connection) -> list[Item]:
        """Zapisany układ; nieznane klucze odpadają, nowe pozycje są widoczne i stają za swoim
        poprzednikiem z domyślnej kolejności (bez niego — na końcu)."""
        saved = db.kv_get(conn, self.kv_key) or {}
        keys = list(self.items)
        order = [k for k in saved.get("order", []) if k in self.items and k not in self.pinned]
        for i, k in enumerate(keys):
            if k not in order and k not in self.pinned:
                prev = keys[i - 1] if i else None
                order.insert(order.index(prev) + 1 if prev in order else len(order), k)
        hidden = set(saved.get("hidden", [])) - set(self.pinned)
        order = [*self.pinned, *order]
        return [Item(k, self.items[k], k in hidden, k in self.pinned) for k in order]

    def _save(self, conn: sqlite3.Connection, items: list[Item]) -> None:
        db.kv_set(
            conn,
            self.kv_key,
            {"order": [t.key for t in items], "hidden": [t.key for t in items if t.hidden]},
        )

    def move(self, conn: sqlite3.Connection, key: str, delta: int) -> None:
        """Przesuwa pozycję o `delta` miejsc; na brzegu (i przypięta) nic się nie dzieje."""
        items = self.load(conn)
        i = next(n for n, t in enumerate(items) if t.key == key)
        j = i + delta
        if not items[i].pinned and len(self.pinned) <= j < len(items):
            items[i], items[j] = items[j], items[i]
            self._save(conn, items)

    def toggle(self, conn: sqlite3.Connection, key: str) -> None:
        items = self.load(conn)
        self._save(
            conn,
            [
                t._replace(hidden=not t.hidden) if t.key == key and not t.pinned else t
                for t in items
            ],
        )

    def reset(self, conn: sqlite3.Connection) -> None:
        db.kv_set(conn, self.kv_key, None)
