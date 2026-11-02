"""Podsumowanie roku (M25 E2): sumy, r/r, zmiany kategorii, rekordy, stopa oszczędności."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from budget import recap, spending

from .test_categorize_engine import add, conn
from .test_piggy import move
from .test_savings import make

__all__ = ["conn"]

TODAY = date(2026, 11, 2)
D = Decimal


def split(conn: sqlite3.Connection, txn: int, parts: tuple[tuple[int, int, str], ...]) -> None:
    for line, cat, amount in parts:
        conn.execute(
            "INSERT INTO txn_split (txn_id, line, category_id, amount, source) "
            "VALUES (?, ?, ?, ?, 'manual')",
            (txn, line, cat, amount),
        )


def test_closed_year_totals_months_and_yoy(conn: sqlite3.Connection) -> None:
    add(conn, "3000", "transfer_in", "Pensja", day="2024-01-01")  # pierwszy dzień: r/r istnieje
    add(conn, "-400", "card", "A", day="2024-03-10", category_id=110)
    add(conn, "-70", "card", "B", day="2024-12-31")  # ostatni dzień poprzedniego roku
    add(conn, "-20", "card", "C", day="2025-01-01", category_id=110)  # pierwszy dzień roku
    add(conn, "5000", "transfer_in", "Pensja", day="2025-01-10")
    add(conn, "-1000", "card", "D", day="2025-02-03", category_id=110)
    add(conn, "-300", "card", "E", day="2025-02-05", category_id=111)
    add(conn, "-50", "card", "F", day="2025-12-31")  # bez kategorii
    add(conn, "-999", "card", "G", day="2026-01-01", category_id=110)  # poza rokiem
    r = recap.build(conn, 2025, TODAY)
    assert r.year == 2025 and r.partial is False
    assert (r.start, r.end) == (date(2025, 1, 1), date(2026, 1, 1))
    assert (r.income, r.expenses) == (D("5000"), D("1370"))
    assert r.prev is not None
    assert (r.prev.income, r.prev.expenses) == (D("3000"), D("470"))  # cały 2024 wliczony
    assert len(r.months) == 12 and r.months[0].month == date(2025, 1, 1)
    assert not any(m.partial for m in r.months)
    feb = r.months[1]
    assert (feb.income, feb.expenses) == (D(0), D("1300"))
    assert r.months[-1].expenses == D("50")
    assert sum((m.expenses for m in r.months), D(0)) == r.expenses


def test_current_year_window_and_same_days_comparison(conn: sqlite3.Connection) -> None:
    add(conn, "1000", "transfer_in", "Pensja", day="2025-01-01")  # początek księgi
    add(conn, "-200", "card", "A", day="2025-10-31", category_id=110)  # w porównaniu
    add(conn, "-500", "card", "B", day="2025-11-03", category_id=110)  # poza porównaniem
    add(conn, "-100", "card", "C", day="2026-03-01", category_id=110)
    add(conn, "-50", "card", "D", day="2026-11-02", category_id=110)  # dziś: w zakresie
    add(conn, "-7", "card", "E", day="2026-11-03", category_id=110)  # jutro: poza zakresem
    r = recap.build(conn, 2026, TODAY)
    assert r.partial is True and r.end == date(2026, 11, 3)
    assert r.expenses == D("150")
    assert r.prev is not None and r.prev.end == date(2025, 11, 3)
    assert r.prev.expenses == D("200")
    assert (r.months[10].partial, r.months[10].expenses) == (True, D("50"))
    assert r.months[11] == spending.MonthTotals(date(2026, 12, 1), D(0), D(0), False)


def test_no_prev_year_means_no_comparison(conn: sqlite3.Connection) -> None:
    add(conn, "-100", "card", "A", day="2025-03-01", category_id=110)
    add(conn, "-300", "card", "B", day="2025-04-01", category_id=120)
    r = recap.build(conn, 2025, TODAY)
    assert r.prev is None
    assert r.rises == [] and r.falls == []
    assert r.expenses == D("400")


def test_changes_net_refunds_and_threshold(conn: sqlite3.Connection) -> None:
    add(conn, "1000", "transfer_in", "Pensja", day="2024-01-01")
    add(conn, "-200", "card", "A", day="2024-05-01", category_id=110)
    add(conn, "-500", "card", "B", day="2025-05-01", category_id=110)
    add(conn, "100", "card_refund", "Zwrot", day="2025-06-01", category_id=110)  # zmniejsza
    add(conn, "-800.01", "card", "C", day="2024-06-01", category_id=120)
    add(conn, "-1000", "card", "D", day="2025-06-01", category_id=120)  # delta 199,99: poniżej
    add(conn, "-400", "card", "E", day="2024-07-01", category_id=130)
    add(conn, "-100", "card", "F", day="2025-07-01", category_id=130)  # delta -300: spadek
    add(conn, "-200", "card", "G", day="2024-08-01", category_id=140)
    add(conn, "-0.01", "card", "H", day="2025-08-01", category_id=140)  # delta -199,99: poniżej
    r = recap.build(conn, 2025, TODAY)
    assert [(c.category.id, c.amount, c.prev) for c in r.rises] == [(2, D("400"), D("200"))]
    assert [(c.category.id, c.amount, c.prev) for c in r.falls] == [(4, D("100"), D("400"))]
    assert r.rises[0].delta == D("200")


def test_top_five_rises(conn: sqlite3.Connection) -> None:
    add(conn, "1000", "transfer_in", "Pensja", day="2024-01-01")
    leaves = (110, 120, 130, 140, 150, 160)  # główne 2..7
    for i, leaf in enumerate(leaves):  # prev 100, delta 100*(i+2): 200..700
        add(conn, "-100", "card", "P", day="2024-02-01", category_id=leaf)
        add(conn, str(-(300 + 100 * i)), "card", "C", day="2025-02-01", category_id=leaf)
    r = recap.build(conn, 2025, TODAY)
    assert [c.category.id for c in r.rises] == [7, 6, 5, 4, 3]
    assert [c.delta for c in r.rises] == [D("700"), D("600"), D("500"), D("400"), D("300")]
    assert r.falls == []


def test_records_biggest_expense_income_and_days_months(conn: sqlite3.Connection) -> None:
    add(conn, "5000", "transfer_in", "Wypłata", "FIRMA", day="2025-01-10", merchant="Pracodawca")
    add(conn, "-700", "card", "A", day="2025-04-04", category_id=110, merchant="Sklep X")
    add(conn, "-300", "card", "B", day="2025-02-03", category_id=110, merchant="Sklep Y")
    add(conn, "-500", "card", "C", day="2025-02-03", category_id=111, merchant="Sklep Z")
    add(conn, "-20", "card", "D", day="2025-02-10", category_id=160)
    add(conn, "300", "card_refund", "Zwrot", day="2025-02-11", category_id=110)  # zwrot netto
    add(conn, "-40", "card", "E", day="2025-02-12", category_id=220)  # oszczędności: nie wydatek
    r = recap.build(conn, 2025, TODAY)
    rec = r.records
    assert rec.biggest_expense == recap.Pick(date(2025, 4, 4), "Sklep X", D("700"))
    assert rec.biggest_income == recap.Pick(date(2025, 1, 10), "Pracodawca", D("5000"))
    assert rec.priciest_day == (date(2025, 2, 3), D("800"))
    assert rec.priciest_month == (date(2025, 4, 1), D("700"))  # kwiecień > luty (520 netto)


def test_split_transaction_counts_once_in_merchants_and_records(
    conn: sqlite3.Connection,
) -> None:
    t = add(conn, "-100", "card", "M", day="2025-03-04", category_id=110, merchant="Sklep M")
    split(conn, t, ((0, 110, "-60.00"), (1, 111, "-40.00")))
    r = recap.build(conn, 2025, TODAY)
    assert [(m.label, m.amount, m.count) for m in r.merchants] == [("Sklep M", D("100"), 1)]
    assert r.records.biggest_expense == recap.Pick(date(2025, 3, 4), "Sklep M", D("100"))
    assert r.expenses == D("100")


def test_flex_free_streak_with_gaps_and_unclassified(conn: sqlite3.Connection) -> None:
    add(conn, "-200", "card", "A", day="2026-01-02", category_id=120)  # stały: nie przerywa
    add(conn, "-10", "card", "B", day="2026-01-05", category_id=110)  # elastyczny
    add(conn, "-1", "card", "C", day="2026-01-06")  # bez kategorii: przerywa
    add(conn, "-10", "card", "D", day="2026-01-15", category_id=110)
    add(conn, "-999", "card", "E", day="2026-01-21", category_id=110)  # jutro: poza zakresem
    r = recap.build(conn, 2026, date(2026, 1, 20))
    assert r.records.flex_free == recap.Streak(date(2026, 1, 7), date(2026, 1, 14), 8)


def test_savings_rate_over_year(conn: sqlite3.Connection) -> None:
    make(conn)
    add(conn, "5000", "transfer_in", "wypłata", "PRACODAWCA", day="2025-02-05")
    move(conn, "-1000", "2025-02-10")  # wpłata na konto oszczędnościowe
    move(conn, "250", "2025-02-20")  # wypłata z niego
    r = recap.build(conn, 2025, TODAY)
    assert r.savings_rate == D("0.15")  # 750 / 5000
    assert r.best_month is not None and r.best_month.month == date(2025, 2, 1)
    assert r.worst_month == r.best_month


def test_years_from_first_day_to_today(conn: sqlite3.Connection) -> None:
    assert recap.years(conn, TODAY) == []
    add(conn, "-10", "card", "A", day="2024-03-01")
    add(conn, "-10", "card", "B", day="2025-06-01")
    assert recap.years(conn, TODAY) == [2026, 2025, 2024]
    assert recap.years(conn, date(2025, 6, 1)) == [2025, 2024]


def test_flex_free_streak_starts_at_first_transaction(conn: sqlite3.Connection) -> None:
    add(conn, "-10", "card", "A", day="2026-03-01", category_id=110)
    r = recap.build(conn, 2026, TODAY)
    assert r.records.flex_free is not None
    assert r.records.flex_free.start >= date(2026, 3, 1)
