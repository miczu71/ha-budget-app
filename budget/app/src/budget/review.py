"""Kolejka „Do przejrzenia”: transakcje bez kategorii pogrupowane do decyzji jednym ruchem.

W kolejce jest wszystko, czego silnik nie skategoryzował (zaksięgowane, bez przelewów
wewnętrznych, konta liczone do budżetu) — bez osobnego stanu „przejrzane”: kolejka znika
sama, gdy reguła albo ręczna kategoria obejmie transakcję.

Grupy:
- **kraj** — zagraniczne płatności kartą (`countries.card_origin`), np. z wyjazdu;
- **sprzedawca** — reszta, po (`txn.merchant`, kierunek, waluta); reguła z kolejki dostaje
  warunek kierunku, więc wydatek i wpływ od tej samej osoby to osobne decyzje.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from budget.countries import card_origin

GroupKind = Literal["merchant", "country"]
Direction = Literal["out", "in"]
Sort = Literal["amount", "count"]
DIRECTIONS: tuple[Direction, ...] = ("out", "in")
SORTS: tuple[Sort, ...] = ("amount", "count")
NO_NAME = "(bez nazwy)"

_WHERE = (
    "t.status = 'BOOK' AND t.transfer_group IS NULL AND t.category_id IS NULL "
    "AND a.include_in_budget = 1"
)


@dataclass(frozen=True)
class GroupKey:
    """Adres grupy w panelu (parametry formularzy i linków)."""

    kind: GroupKind
    value: str  # nazwa sprzedawcy albo `Origin.key`
    direction: Direction
    currency: str


@dataclass(frozen=True)
class Item:
    id: int
    day: str
    amount: Decimal
    currency: str
    merchant: str
    description: str
    account_id: int


@dataclass
class Group:
    key: GroupKey
    label: str
    items: list[Item] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.items)

    @property
    def total(self) -> Decimal:
        """Suma wartości bezwzględnych."""
        return sum((abs(i.amount) for i in self.items), Decimal(0))

    @property
    def first_day(self) -> str:
        return min(i.day for i in self.items)

    @property
    def last_day(self) -> str:
        return max(i.day for i in self.items)

    @property
    def can_rule(self) -> bool:
        """Reguła „sprzedawca równa się” tylko dla nazwanego sprzedawcy."""
        return self.key.kind == "merchant" and self.key.value != ""

    def merchants(self) -> list[tuple[str, list[Item]]]:
        """Pozycje grupy kraju podzielone po sprzedawcy (najwięcej pozycji najpierw)."""
        by: dict[str, list[Item]] = {}
        for i in self.items:
            by.setdefault(i.merchant, []).append(i)
        return sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0]))


@dataclass
class Queue:
    countries: list[Group]
    merchants: list[Group]
    merchants_total: int  # wszystkie grupy sprzedawców przed obcięciem do `limit`
    pending: int  # wszystkie pozycje kolejki (oba kierunki)


def _items(conn: sqlite3.Connection) -> Iterable[tuple[sqlite3.Row, Item]]:
    rows = conn.execute(
        "SELECT t.id, coalesce(t.tx_date, t.booking_date) AS day, t.amount, t.currency, "
        "t.merchant, t.description, t.account_id, t.kind, t.orig_currency "
        f"FROM txn t JOIN account a ON a.id = t.account_id WHERE {_WHERE} "
        "ORDER BY day DESC, t.id DESC"
    )
    for r in rows:
        yield (
            r,
            Item(
                id=int(r["id"]),
                day=str(r["day"] or ""),
                amount=Decimal(r["amount"]),
                currency=str(r["currency"]),
                merchant=str(r["merchant"] or ""),
                description=str(r["description"] or ""),
                account_id=int(r["account_id"]),
            ),
        )


def _direction(amount: Decimal) -> Direction:
    return "out" if amount < 0 else "in"


def all_groups(conn: sqlite3.Connection) -> list[Group]:
    """Wszystkie grupy kolejki (oba kierunki), pozycje od najnowszej."""
    groups: dict[GroupKey, Group] = {}
    for r, item in _items(conn):
        direction = _direction(item.amount)
        origin = card_origin(str(r["kind"]), r["description"], r["orig_currency"])
        if origin is not None:
            key = GroupKey("country", origin.key, direction, item.currency)
            label = origin.label
        else:
            key = GroupKey("merchant", item.merchant, direction, item.currency)
            label = item.merchant or NO_NAME
        groups.setdefault(key, Group(key, label)).items.append(item)
    return list(groups.values())


def _sorted(groups: list[Group], sort: Sort) -> list[Group]:
    if sort == "count":
        return sorted(groups, key=lambda g: (-g.count, -g.total, g.label))
    return sorted(groups, key=lambda g: (-g.total, -g.count, g.label))


def queue(
    conn: sqlite3.Connection, direction: Direction = "out", sort: Sort = "amount", limit: int = 50
) -> Queue:
    groups = all_groups(conn)
    pending = sum(g.count for g in groups)
    chosen = [g for g in groups if g.key.direction == direction]
    merchants = _sorted([g for g in chosen if g.key.kind == "merchant"], sort)
    return Queue(
        countries=_sorted([g for g in chosen if g.key.kind == "country"], sort),
        merchants=merchants[:limit],
        merchants_total=len(merchants),
        pending=pending,
    )


def group(conn: sqlite3.Connection, key: GroupKey) -> Group | None:
    """Bieżący stan jednej grupy; `None`, gdy nic z niej nie zostało w kolejce."""
    return next((g for g in all_groups(conn) if g.key == key), None)


def pending_count(conn: sqlite3.Connection) -> int:
    """Liczba transakcji do przejrzenia (nawigacja panelu, podsumowania M6)."""
    row = conn.execute(
        f"SELECT count(*) FROM txn t JOIN account a ON a.id = t.account_id WHERE {_WHERE}"
    ).fetchone()
    return int(row[0])
