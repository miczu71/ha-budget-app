"""Taksonomia: seed z migracji, drzewo, dodanie i zmiana nazwy podkategorii."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from budget.categorize import taxonomy
from budget.categorize.taxonomy import TaxonomyError
from budget.storage import db


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = db.connect(":memory:")
    yield c
    c.close()


def test_seed_two_levels(conn: sqlite3.Connection) -> None:
    tree = taxonomy.tree(conn)
    assert [m.category.slug for m in tree][:2] == ["przychody", "jedzenie"]
    assert len(tree) == 14
    assert all(m.children for m in tree), "każda główna ma podkategorie"
    leaves = taxonomy.leaves(conn)
    assert len(leaves) >= 40
    assert all(c.flex_group in taxonomy.FLEX_GROUPS for c in leaves.values())
    assert all(m.category.flex_group is None for m in tree)


def test_seed_groups(conn: sqlite3.Connection) -> None:
    slugs = taxonomy.by_slug(conn)
    assert slugs["wynagrodzenie"].flex_group == "income"
    assert slugs["kredyt"].flex_group == "fixed"
    assert slugs["inwestycje"].flex_group == "savings"
    assert slugs["jednorazowe"].flex_group == "excluded"


def test_main_category_needs_no_group_and_leaf_needs_one(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO category (parent_id, slug, name) VALUES (2, 'x', 'X')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO category (parent_id, slug, name, flex_group) "
            "VALUES (NULL, 'y', 'Y', 'fixed')"
        )


def test_add_subcategory(conn: sqlite3.Connection) -> None:
    new_id = taxonomy.add_subcategory(conn, 4, "  Rower  i hulajnoga ")
    cat = taxonomy.leaves(conn)[new_id]
    assert cat.name == "Rower i hulajnoga"
    assert cat.slug == "rower-i-hulajnoga"
    assert cat.flex_group == "non_monthly"  # jak ostatnia podkategoria transportu
    assert taxonomy.tree(conn)[3].children[-1].id == new_id


def test_add_subcategory_slug_unique_and_polish(conn: sqlite3.Connection) -> None:
    a = taxonomy.add_subcategory(conn, 2, "Żłobek", "fixed")
    b = taxonomy.add_subcategory(conn, 6, "żłobek")
    leaves = taxonomy.leaves(conn)
    assert leaves[a].slug == "zlobek"
    assert leaves[b].slug == "zlobek-2"
    assert leaves[a].flex_group == "fixed"


@pytest.mark.parametrize(
    ("parent", "name", "message"),
    [
        (100, "X", "głównej"),
        (999, "X", "głównej"),
        (2, "  ", "pusta"),
        (2, "x" * 61, "60"),
        (2, "spożywcze", "już istnieje"),
    ],
)
def test_add_subcategory_errors(
    conn: sqlite3.Connection, parent: int, name: str, message: str
) -> None:
    with pytest.raises(TaxonomyError, match=message):
        taxonomy.add_subcategory(conn, parent, name)


def test_add_subcategory_bad_group(conn: sqlite3.Connection) -> None:
    with pytest.raises(TaxonomyError, match="grupa"):
        taxonomy.add_subcategory(conn, 2, "Nowa", "zła")


def test_rename_keeps_slug(conn: sqlite3.Connection) -> None:
    taxonomy.rename(conn, 110, "Zakupy spożywcze")
    cat = taxonomy.leaves(conn)[110]
    assert (cat.name, cat.slug) == ("Zakupy spożywcze", "spozywcze")
    taxonomy.rename(conn, 110, "zakupy SPOŻYWCZE")  # ta sama kategoria — bez konfliktu
    with pytest.raises(TaxonomyError, match="już istnieje"):
        taxonomy.rename(conn, 111, "Zakupy spożywcze")
    with pytest.raises(TaxonomyError, match="Nie ma"):
        taxonomy.rename(conn, 999, "X")
