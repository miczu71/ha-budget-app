"""Kolejka „Do przejrzenia”: transakcje bez kategorii pogrupowane do decyzji jednym ruchem.

W kolejce jest wszystko, czego silnik nie skategoryzował (zaksięgowane, bez przelewów
wewnętrznych, konta liczone do budżetu) — bez osobnego stanu „przejrzane”: kolejka znika
sama, gdy reguła albo ręczna kategoria obejmie transakcję.

Grupy:
- **kraj** — zagraniczne płatności kartą (`countries.card_origin`) u sprzedawców
  sporadycznych, czyli zwykle wyjazd; zagraniczny sprzedawca obecny w co najmniej
  `REGULAR_MONTHS` różnych miesiącach (subskrypcja, doładowania) to stała usługa — trafia do
  grup sprzedawców, gdzie reguła ma sens;
- **sprzedawca** — reszta, po (`txn.merchant`, kierunek, waluta); reguła z kolejki dostaje
  warunek kierunku, więc wydatek i wpływ od tej samej osoby to osobne decyzje.

Osobno sekcja **przypisane automatycznie** (`learned`): pozycje z kategorią z pamięci sprzedawcy
(M7 E2) — już liczone w budżecie, ale do zerknięcia; potwierdzenie albo poprawka to kategoria
ręczna.

Widok miesiąca (link z ekranu „Wydatki”) pokazuje tylko pozycje z danego miesiąca (data
transakcji, jak na „Wydatkach”); to, czy sprzedawca zagraniczny jest stały, liczy się zawsze na
całej historii, więc grupy nie zmieniają rodzaju zależnie od oglądanego miesiąca.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from budget.categorize import taxonomy
from budget.countries import card_origin

GroupKind = Literal["merchant", "country"]
Direction = Literal["out", "in"]
Sort = Literal["amount", "count"]
DIRECTIONS: tuple[Direction, ...] = ("out", "in")
SORTS: tuple[Sort, ...] = ("amount", "count")
NO_NAME = "(bez nazwy)"
REGULAR_MONTHS = 3

# Transakcje, które mogą trafić do kolejki (alias `t` dla txn, `a` dla account) — też
# `budget.categorize.learn`; czekające na kategorię — też `budget.suggest`
QUEUE_SCOPE = "t.status = 'BOOK' AND t.transfer_group IS NULL AND a.include_in_budget = 1"
PENDING_WHERE = f"{QUEUE_SCOPE} AND t.category_id IS NULL"
LEARNED_WHERE = f"{QUEUE_SCOPE} AND t.category_source = 'learned'"


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
    def default_merchant(self) -> str:
        """Sprzedawca domyślnego warunku reguły: nazwa grupy sprzedawcy, w grupie kraju
        najczęstszy sprzedawca; "" — grupa bez nazwy (warunek trzeba wpisać)."""
        if self.key.kind == "merchant":
            return self.key.value
        return self.merchants()[0][0] if self.items else ""

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
    pending: int  # wszystkie pozycje kolejki (oba kierunki; w widoku miesiąca — z miesiąca)


@dataclass(frozen=True)
class LearnedKey:
    merchant: str
    direction: Direction
    currency: str
    category_id: int


@dataclass
class Learned:
    """Grupa „przypisane automatycznie”: (sprzedawca, kierunek, waluta, kategoria z pamięci)."""

    key: LearnedKey
    category: str  # nazwa podkategorii
    items: list[Item] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.key.merchant or NO_NAME

    @property
    def count(self) -> int:
        return len(self.items)

    @property
    def total(self) -> Decimal:
        return sum((abs(i.amount) for i in self.items), Decimal(0))


def _items(
    conn: sqlite3.Connection, where: str = PENDING_WHERE
) -> Iterable[tuple[sqlite3.Row, Item]]:
    rows = conn.execute(
        "SELECT t.id, coalesce(t.tx_date, t.booking_date) AS day, t.amount, t.currency, "
        "t.merchant, t.description, t.account_id, t.kind, t.orig_currency, t.category_id "
        f"FROM txn t JOIN account a ON a.id = t.account_id WHERE {where} "
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


def direction(amount: Decimal) -> Direction:
    return "out" if amount < 0 else "in"


def all_groups(conn: sqlite3.Connection, month: date | None = None) -> list[Group]:
    """Wszystkie grupy kolejki (oba kierunki), pozycje od najnowszej; `month` — tylko pozycje
    z miesiąca, w którym leży ta data."""
    rows = [
        (item, card_origin(str(r["kind"]), r["description"], r["orig_currency"]))
        for r, item in _items(conn)
    ]
    months: dict[str, set[str]] = {}
    for item, origin in rows:
        if origin is not None:
            months.setdefault(item.merchant, set()).add(item.day[:7])
    regular = {m for m, ms in months.items() if m and len(ms) >= REGULAR_MONTHS}
    prefix = month.strftime("%Y-%m") if month else ""
    groups: dict[GroupKey, Group] = {}
    for item, origin in rows:
        if not item.day.startswith(prefix):
            continue
        way = direction(item.amount)
        if origin is not None and item.merchant not in regular:
            key = GroupKey("country", origin.key, way, item.currency)
            label = origin.label
        else:
            key = GroupKey("merchant", item.merchant, way, item.currency)
            label = item.merchant or NO_NAME
        groups.setdefault(key, Group(key, label)).items.append(item)
    return list(groups.values())


def _sorted(groups: list[Group], sort: Sort) -> list[Group]:
    if sort == "count":
        return sorted(groups, key=lambda g: (-g.count, -g.total, g.label))
    return sorted(groups, key=lambda g: (-g.total, -g.count, g.label))


def queue(
    conn: sqlite3.Connection,
    direction: Direction = "out",
    sort: Sort = "amount",
    limit: int = 50,
    month: date | None = None,
    only: Collection[str] | None = None,
) -> Queue:
    """`only` — tylko grupy tych sprzedawców (filtr po propozycji AI), bez grup kraju."""
    groups = all_groups(conn, month)
    pending = sum(g.count for g in groups)
    chosen = [g for g in groups if g.key.direction == direction]
    merchants = _sorted(
        [g for g in chosen if g.key.kind == "merchant" and (only is None or g.key.value in only)],
        sort,
    )
    countries = [] if only is not None else [g for g in chosen if g.key.kind == "country"]
    return Queue(
        countries=_sorted(countries, sort),
        merchants=merchants[:limit],
        merchants_total=len(merchants),
        pending=pending,
    )


def group(conn: sqlite3.Connection, key: GroupKey, month: date | None = None) -> Group | None:
    """Bieżący stan jednej grupy (w widoku miesiąca: jej pozycje z miesiąca); `None`, gdy nic
    z niej nie zostało w kolejce."""
    return next((g for g in all_groups(conn, month) if g.key == key), None)


def learned(conn: sqlite3.Connection, way: Direction, month: date | None = None) -> list[Learned]:
    """Pozycje z pamięci sprzedawcy w kierunku `way` (w widoku miesiąca — z miesiąca), największe
    grupy najpierw."""
    prefix = month.strftime("%Y-%m") if month else ""
    names = taxonomy.all_categories(conn)
    groups: dict[LearnedKey, Learned] = {}
    for r, item in _items(conn, LEARNED_WHERE):
        if direction(item.amount) != way or not item.day.startswith(prefix):
            continue
        key = LearnedKey(item.merchant, way, item.currency, int(r["category_id"]))
        groups.setdefault(key, Learned(key, names[key.category_id].name)).items.append(item)
    return sorted(groups.values(), key=lambda g: (-g.total, g.key.merchant))


def learned_group(
    conn: sqlite3.Connection, key: LearnedKey, month: date | None = None
) -> Learned | None:
    """Bieżący stan jednej grupy „przypisane automatycznie”; `None`, gdy już przejrzana."""
    return next((g for g in learned(conn, key.direction, month) if g.key == key), None)


def pending_count(conn: sqlite3.Connection) -> int:
    """Liczba transakcji do przejrzenia (nawigacja panelu, podsumowania M6)."""
    row = conn.execute(
        f"SELECT count(*) FROM txn t JOIN account a ON a.id = t.account_id WHERE {PENDING_WHERE}"
    ).fetchone()
    return int(row[0])
