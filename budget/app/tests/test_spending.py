"""Wydatki miesiąca: sekcje, zwroty netto, wykluczenia, granice miesiąca, pokrycie."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from budget import spending
from budget.categorize import engine, taxonomy

from .test_categorize_engine import add, conn, sid

__all__ = ["conn"]


def build(
    c: sqlite3.Connection, month: str = "2026-09-01", today: str = "2026-09-20"
) -> spending.Month:
    engine.recategorize(c)
    return spending.build(c, date.fromisoformat(month), date.fromisoformat(today))


def test_sections_and_identity(conn: sqlite3.Connection) -> None:
    buy = add(conn, "-100.00", "card", "LIDL XYZ POL 2026-09-02", day="2026-09-02")
    add(conn, "20.00", "card_refund", "LIDL XYZ POL 2026-09-05", day="2026-09-05", refund_of=buy)
    add(conn, "-60.00", "card", "ORLEN STACJA XYZ", day="2026-09-03")
    add(conn, "-40.00", "card", "SKLEP ABC XYZ", day="2026-09-04")  # bez kategorii
    add(conn, "5000.00", "transfer_in", "Pensja", "FIRMA X", day="2026-09-10")
    add(conn, "150.00", "transfer_in", "Zwrot", "JAN NOWAK", day="2026-09-11")  # bez kategorii
    sav = add(conn, "-1000.00", "transfer_out", "Lokata", "JA SAM", day="2026-09-12")
    big = add(conn, "-3000.00", "transfer_out", "Auto", "SALON", day="2026-09-13")
    add(conn, "-700.00", "card_repayment", "", None, day="2026-09-14", transfer_group="t1")
    add(conn, "-9.00", "card", "LIDL XYZ", day="2026-09-15", currency="EUR")
    engine.set_manual(conn, sav, sid(conn, "oszczednosci-przelewy"))
    engine.set_manual(conn, big, sid(conn, "jednorazowe"))
    engine.set_manual(
        conn, add(conn, "1.00", "fee", "ZWROT OPLATY", day="2026-09-16"), sid(conn, "wynagrodzenie")
    )
    m = build(conn)

    groups = {g.category.slug: g for g in m.expense_groups}
    assert [g.category.slug for g in m.expense_groups] == ["jedzenie", "transport"]
    assert groups["jedzenie"].amount == Decimal("80.00")  # zwrot netto
    assert groups["jedzenie"].count == 2
    assert [c.category.slug for c in groups["jedzenie"].children] == ["spozywcze"]
    assert m.uncategorized_out == Decimal("40.00") and m.uncategorized_out_count == 1
    assert m.expenses == Decimal("180.00")
    assert groups["jedzenie"].share == 80 / 180
    assert m.uncategorized_in == Decimal("5150.00")  # pensja bez reguły + zwrot od osoby
    assert m.income == Decimal("5151.00")  # 1 zł w kategorii przychodu + nieskategoryzowane
    assert m.savings == Decimal("1000.00")
    assert m.excluded == Decimal("3000.00")
    assert m.other_currency == 1
    # przelew wewnętrzny (spłata karty) nie wchodzi nigdzie
    assert m.balance == m.income - m.expenses - m.savings - m.excluded
    assert m.balance == Decimal("971.00")
    assert m.income_lines[0].category.slug == "wynagrodzenie"
    # pokrycie: 6 wydatków PLN (bez przelewu wewn.), 5 w kategoriach
    assert (m.coverage.txns, m.coverage.categorized) == (5, 4)


def test_month_boundaries_and_prev(conn: sqlite3.Connection) -> None:
    add(conn, "-10.00", "card", "LIDL A", day="2026-08-31")
    add(conn, "-30.00", "card", "LIDL B", day="2026-09-01")
    # zakup 30.09, zaksięgowany 01.10 — liczy się wrzesień (data transakcji)
    add(conn, "-5.00", "card", "LIDL C", day="2026-10-01", tx_date="2026-09-30")
    m = build(conn)
    food = m.expense_groups[0]
    assert (food.amount, food.prev, food.delta) == (
        Decimal("35.00"),
        Decimal("10.00"),
        Decimal("25.00"),
    )
    assert (m.month, m.prev_month, m.next_month) == (date(2026, 9, 1), date(2026, 8, 1), None)
    assert build(conn, "2026-08-01").next_month == date(2026, 9, 1)
    assert build(conn, "2025-12-15", today="2026-09-20").prev_month == date(2025, 11, 1)


def test_excluded_account_and_empty_month(conn: sqlite3.Connection) -> None:
    add(conn, "-30.00", "card", "LIDL B", day="2026-09-01", account=2)
    conn.execute("UPDATE account SET include_in_budget = 0 WHERE id = 2")
    m = build(conn)
    assert m.expense_groups == [] and m.expenses == 0 and m.coverage.pct_txns == 0.0


def test_coverage_whole_ledger(conn: sqlite3.Connection) -> None:
    add(conn, "-30.00", "card", "LIDL B", day="2026-01-01")
    add(conn, "-70.00", "card", "SKLEP ABC", day="2026-05-01")
    add(conn, "100.00", "transfer_in", "X", "Y", day="2026-05-01")
    engine.recategorize(conn)
    cov = spending.coverage(conn)
    assert (cov.txns, cov.categorized, cov.pct_txns, cov.pct_amount) == (2, 1, 0.5, 0.3)


def test_add_months() -> None:
    assert spending.add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert spending.add_months(date(2026, 12, 1), 1) == date(2027, 1, 1)


def test_moved_subcategory_counts_under_new_main(conn: sqlite3.Connection) -> None:
    add(conn, "-100.00", "card", "LIDL XYZ POL", day="2026-08-10")
    add(conn, "-60.00", "card", "ORLEN STACJA XYZ", day="2026-09-03")
    add(conn, "-40.00", "card", "LIDL XYZ POL", day="2026-09-04")
    engine.recategorize(conn)
    groceries = taxonomy.by_slug(conn)["spozywcze"]
    before = conn.execute("SELECT id, category_id FROM txn ORDER BY id").fetchall()
    shop = taxonomy.add_main(conn, "Zakupy codzienne")
    taxonomy.move(conn, groceries.id, shop)
    assert conn.execute("SELECT id, category_id FROM txn ORDER BY id").fetchall() == before

    m = build(conn)
    groups = {g.category.slug: g for g in m.expense_groups}
    assert set(groups) == {"zakupy-codzienne", "transport"}
    assert groups["zakupy-codzienne"].amount == Decimal("40.00")
    assert groups["zakupy-codzienne"].prev == Decimal("100.00")  # poprzedni miesiąc też
