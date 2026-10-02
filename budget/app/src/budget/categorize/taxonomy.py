"""Kategorie dwupoziomowe: główne grupują podkategorie, transakcja dostaje podkategorię.

Seed jest w migracji `003_categories.sql`; słownik sieci i reguły odwołują się do podkategorii
po `slug` / `id`. W M4a panel pozwala dodać podkategorię i zmienić nazwę, resztę (przenoszenie,
usuwanie, grupy Flex) dostanie M5.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from budget.normalize import fold

FLEX_GROUPS = ("income", "fixed", "flexible", "non_monthly", "savings", "excluded")
FLEX_LABELS = {
    "income": "przychody",
    "fixed": "stałe",
    "flexible": "elastyczne",
    "non_monthly": "nieregularne",
    "savings": "oszczędności",
    "excluded": "poza budżetem",
}
NAME_MAX = 60


class TaxonomyError(ValueError):
    """Komunikat dla użytkownika panelu."""


@dataclass(frozen=True)
class Category:
    id: int
    parent_id: int | None
    slug: str
    name: str
    flex_group: str | None
    sort: int

    @property
    def is_main(self) -> bool:
        return self.parent_id is None


@dataclass
class MainCategory:
    category: Category
    children: list[Category] = field(default_factory=list)


def _row(r: sqlite3.Row) -> Category:
    return Category(
        id=int(r["id"]),
        parent_id=r["parent_id"],
        slug=r["slug"],
        name=r["name"],
        flex_group=r["flex_group"],
        sort=int(r["sort"]),
    )


def all_categories(conn: sqlite3.Connection) -> dict[int, Category]:
    rows = conn.execute("SELECT * FROM category ORDER BY sort, id")
    return {int(r["id"]): _row(r) for r in rows}


def tree(conn: sqlite3.Connection) -> list[MainCategory]:
    """Kategorie główne w kolejności `sort`, każda z podkategoriami."""
    cats = all_categories(conn)
    mains = {c.id: MainCategory(c) for c in cats.values() if c.is_main}
    for c in cats.values():
        if c.parent_id is not None:
            mains[c.parent_id].children.append(c)
    return list(mains.values())


def leaves(conn: sqlite3.Connection) -> dict[int, Category]:
    """Podkategorie — jedyne, które można przypisać transakcji."""
    return {i: c for i, c in all_categories(conn).items() if not c.is_main}


def by_slug(conn: sqlite3.Connection) -> dict[str, Category]:
    return {c.slug: c for c in all_categories(conn).values()}


def _clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        raise TaxonomyError("Nazwa kategorii nie może być pusta.")
    if len(name) > NAME_MAX:
        raise TaxonomyError(f"Nazwa kategorii może mieć najwyżej {NAME_MAX} znaków.")
    return name


def _check_unique(conn: sqlite3.Connection, parent_id: int, name: str, skip: int | None) -> None:
    for r in conn.execute("SELECT id, name FROM category WHERE parent_id = ?", (parent_id,)):
        if r["id"] != skip and fold(r["name"]) == fold(name):
            raise TaxonomyError(f"Podkategoria „{name}” już istnieje w tej grupie.")


def _slug(conn: sqlite3.Connection, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", fold(name).lower()).strip("-") or "kategoria"
    taken = {r[0] for r in conn.execute("SELECT slug FROM category")}
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    return slug


def add_subcategory(
    conn: sqlite3.Connection, parent_id: int, name: str, flex_group: str | None = None
) -> int:
    """Nowa podkategoria na końcu grupy; grupa Flex domyślnie jak ostatnia podkategoria."""
    parent = all_categories(conn).get(parent_id)
    if parent is None or not parent.is_main:
        raise TaxonomyError("Nie ma takiej kategorii głównej.")
    name = _clean_name(name)
    _check_unique(conn, parent_id, name, None)
    last = conn.execute(
        "SELECT flex_group, max(sort) AS s FROM category WHERE parent_id = ? GROUP BY parent_id",
        (parent_id,),
    ).fetchone()
    group = flex_group or (last["flex_group"] if last else "flexible")
    if group not in FLEX_GROUPS:
        raise TaxonomyError("Nieznana grupa budżetu.")
    sort = (int(last["s"]) if last else 0) + 10
    cur = conn.execute(
        "INSERT INTO category (parent_id, slug, name, flex_group, sort) VALUES (?, ?, ?, ?, ?)",
        (parent_id, _slug(conn, name), name, group, sort),
    )
    return int(cur.lastrowid or 0)


def rename(conn: sqlite3.Connection, category_id: int, name: str) -> None:
    """Zmiana nazwy (slug zostaje — słownik i reguły się nie rozjeżdżają)."""
    cat = all_categories(conn).get(category_id)
    if cat is None:
        raise TaxonomyError("Nie ma takiej kategorii.")
    name = _clean_name(name)
    if cat.parent_id is not None:
        _check_unique(conn, cat.parent_id, name, cat.id)
    conn.execute("UPDATE category SET name = ? WHERE id = ?", (name, category_id))
