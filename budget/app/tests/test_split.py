"""Podział transakcji na podkategorie (M29 E1)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget import spending, split
from budget.categorize import engine
from budget.categorize.taxonomy import TaxonomyError

from .test_categorize_engine import add, conn, sid

__all__ = ["conn"]


def test_save_keeps_parts_and_largest_category(conn: sqlite3.Connection) -> None:
    t = add(conn, "-100.00", "card", "LIDL XYZ POL", day="2026-09-02")
    engine.recategorize(conn)
    split.save(
        conn,
        t,
        [(sid(conn, "drogeria"), Decimal("-30.00")), (sid(conn, "spozywcze"), Decimal("-70.00"))],
    )
    engine.recategorize(conn)

    assert split.get(conn, t) == [
        (sid(conn, "drogeria"), Decimal("-30.00")),
        (sid(conn, "spozywcze"), Decimal("-70.00")),
    ]
    row = conn.execute("SELECT category_id, category_source FROM txn WHERE id = ?", (t,)).fetchone()
    assert (row["category_id"], row["category_source"]) == (sid(conn, "spozywcze"), "manual")


@pytest.mark.parametrize(
    ("parts", "message"),
    [
        ([("drogeria", "-30.00"), ("spozywcze", "-60.00")], "Zostało do przydzielenia: 10,00"),
        ([("drogeria", "-50.00"), ("spozywcze", "-60.00")], "Przydzielono o 10,00"),
        ([("spozywcze", "-100.00")], "co najmniej dwóch"),
        ([("jedzenie", "-30.00"), ("spozywcze", "-70.00")], "podkategori"),
        ([("drogeria", "30.00"), ("spozywcze", "-130.00")], "znak"),
        ([("drogeria", "0.00"), ("spozywcze", "-100.00")], "znak"),
    ],
)
def test_save_rejects_invalid_parts(
    conn: sqlite3.Connection, parts: list[tuple[str, str]], message: str
) -> None:
    t = add(conn, "-100.00", "card", "LIDL XYZ POL", day="2026-09-02")
    with pytest.raises(TaxonomyError, match=message):
        split.save(conn, t, [(sid(conn, slug), Decimal(a)) for slug, a in parts])
    assert split.get(conn, t) == []


def _split_lidl(conn: sqlite3.Connection) -> int:
    t = add(conn, "-100.00", "card", "LIDL XYZ POL", day="2026-09-02")
    engine.recategorize(conn)
    split.save(
        conn, t, [(sid(conn, "drogeria"), Decimal("-60")), (sid(conn, "spozywcze"), Decimal("-40"))]
    )
    return t


def _category(conn: sqlite3.Connection, t: int) -> tuple[int, str]:
    row = conn.execute("SELECT category_id, category_source FROM txn WHERE id = ?", (t,)).fetchone()
    return row["category_id"], row["category_source"]


def test_clear_restores_automatic_category(conn: sqlite3.Connection) -> None:
    t = _split_lidl(conn)
    split.clear(conn, t)
    engine.recategorize(conn)
    assert split.get(conn, t) == []
    assert _category(conn, t) == (sid(conn, "spozywcze"), "dictionary")


def test_manual_category_replaces_split(conn: sqlite3.Connection) -> None:
    t = _split_lidl(conn)
    engine.set_manual(conn, t, sid(conn, "zakupy-inne"))
    assert split.get(conn, t) == []
    assert _category(conn, t) == (sid(conn, "zakupy-inne"), "manual")
    t2 = _split_lidl(conn)
    engine.set_manual(conn, t2, None)  # „automatyczna” też kasuje podział
    engine.recategorize(conn)
    assert split.get(conn, t2) == []


def test_split_does_not_teach_merchant_memory(conn: sqlite3.Connection) -> None:
    t = add(conn, "-100.00", "card", "SKLEP ABC XYZ", day="2026-09-02")
    other = add(conn, "-20.00", "card", "SKLEP ABC XYZ", day="2026-09-05")
    split.save(
        conn, t, [(sid(conn, "drogeria"), Decimal("-60")), (sid(conn, "spozywcze"), Decimal("-40"))]
    )
    engine.recategorize(conn)
    assert _category(conn, other) == (None, None)


def test_month_counts_each_part_in_its_category(conn: sqlite3.Connection) -> None:
    t = _split_lidl(conn)  # −100: Drogeria −60, Spożywcze −40
    add(conn, "-50.00", "card", "LIDL XYZ POL", day="2026-09-03")
    engine.recategorize(conn)
    before = spending.sums(conn, date(2026, 9, 1), date(2026, 10, 1))
    m = spending.build(conn, date(2026, 9, 1), date(2026, 9, 20))

    groups = {g.category.slug: g.amount for g in m.expense_groups}
    assert groups == {"jedzenie": Decimal("90.00"), "zdrowie": Decimal("60.00")}
    assert m.expenses == Decimal("150.00")
    assert (m.coverage.txns, m.coverage.categorized) == (2, 2)
    split.clear(conn, t)
    engine.recategorize(conn)
    after = spending.sums(conn, date(2026, 9, 1), date(2026, 10, 1))
    assert before.balance == after.balance == Decimal("-150.00")


def test_save_rejects_own_transfer(conn: sqlite3.Connection) -> None:
    t = add(conn, "-700.00", "card_repayment", "", None, day="2026-09-14", transfer_group="t1")
    with pytest.raises(TaxonomyError, match="Przelew"):
        split.save(
            conn,
            t,
            [(sid(conn, "drogeria"), Decimal("-300")), (sid(conn, "spozywcze"), Decimal("-400"))],
        )
