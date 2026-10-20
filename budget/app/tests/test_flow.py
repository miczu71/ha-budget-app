"""Przepływ pieniędzy (M19): bilans węzłów, zgodność z Wydatkami, deficyt, zwroty, pusty miesiąc."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from budget import flow, spending
from budget.categorize import engine

from .test_categorize_engine import add, conn, sid

__all__ = ["conn"]

START, END = date(2026, 9, 1), date(2026, 10, 1)


def build(c: sqlite3.Connection) -> flow.Flow:
    engine.recategorize(c)
    return flow.build(c, START, END)


def assert_balanced(f: flow.Flow) -> None:
    """Każdy węzeł: wejścia = wyjścia (kolumny skrajne mają tylko jedną stronę)."""
    for n in f.nodes:
        out = sum((e.amount for e in f.edges if e.src == n.key), Decimal(0))
        inn = sum((e.amount for e in f.edges if e.dst == n.key), Decimal(0))
        if n.column > 0:
            assert inn == n.amount, n.key
        if n.column < 2 and any(e.src == n.key for e in f.edges):
            assert out == n.amount, n.key


def seed(c: sqlite3.Connection, income: str = "5000.00") -> None:
    buy = add(c, "-100.00", "card", "LIDL XYZ POL 2026-09-02", day="2026-09-02")
    add(c, "20.00", "card_refund", "LIDL XYZ POL 2026-09-05", day="2026-09-05", refund_of=buy)
    add(c, "-60.00", "card", "ORLEN STACJA XYZ", day="2026-09-03")
    add(c, "-40.00", "card", "SKLEP ABC XYZ", day="2026-09-04")  # bez kategorii
    add(c, income, "transfer_in", "Pensja", "FIRMA X", day="2026-09-10")
    sav = add(c, "-1000.00", "transfer_out", "Lokata", "JA SAM", day="2026-09-12")
    big = add(c, "-3000.00", "transfer_out", "Auto", "SALON", day="2026-09-13")
    engine.set_manual(c, sav, sid(c, "oszczednosci-przelewy"))
    engine.set_manual(c, big, sid(c, "jednorazowe"))


def test_matches_spending_and_balances(conn: sqlite3.Connection) -> None:
    seed(conn)
    f = build(conn)
    m = spending.build(conn, START, date(2026, 9, 20))
    assert f.income == m.income
    mains = {n.category_id: n for n in f.nodes if n.column == 2 and n.category_id}
    for g in m.expense_groups:
        assert sum(n.amount for n in mains.values() if n.category_id == g.category.id) == g.amount
    assert f.node("unc").amount == m.uncategorized_out
    assert f.node("g-savings").amount == m.savings
    assert f.outflow == m.expenses + m.savings
    assert f.surplus == f.income - f.outflow and f.deficit == 0
    assert f.node("surplus").amount == f.surplus
    assert_balanced(f)


def test_deficit_source_and_proportional_split(conn: sqlite3.Connection) -> None:
    seed(conn, income="500.00")
    f = build(conn)
    assert f.deficit == f.outflow - f.income > 0
    assert "surplus" not in {n.key for n in f.nodes}
    assert f.node("deficit").amount == f.deficit
    assert sum(e.amount for e in f.edges if e.src == "in") == f.income
    assert sum(e.amount for e in f.edges if e.src == "deficit") == f.deficit
    assert_balanced(f)


def test_net_refund_category_has_no_node(conn: sqlite3.Connection) -> None:
    buy = add(conn, "-10.00", "card", "LIDL XYZ POL 2026-09-02", day="2026-09-02")
    add(conn, "30.00", "card_refund", "LIDL XYZ POL 2026-09-05", day="2026-09-05", refund_of=buy)
    f = build(conn)
    assert [n for n in f.nodes if n.column == 2] == []
    assert f.outflow == 0


def test_top_n_and_other_per_group(conn: sqlite3.Connection) -> None:
    seed(conn)
    f = build(conn)
    cats = [n for n in f.nodes if n.column == 2]
    assert len(cats) <= flow.TOP + len(flow.GROUPS)
    assert all(n.color in {f"c{i}" for i in range(1, 9)} | {"other"} for n in cats)


def test_empty_month(conn: sqlite3.Connection) -> None:
    f = build(conn)
    assert f.nodes == [] and f.edges == [] and f.income == f.outflow == 0
