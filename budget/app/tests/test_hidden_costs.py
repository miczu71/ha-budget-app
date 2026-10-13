"""Koszty ukryte (M23 E3): koszt przewalutowania względem NBP, opłaty banku, pokrycie CSV karty."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from budget import fx, hidden_costs

from .test_categorize_engine import add, conn

__all__ = ["conn"]

SEP = (date(2026, 9, 1), date(2026, 10, 1))


def seed_rates(conn: sqlite3.Connection) -> None:
    fx.store(
        conn, "EUR", {date(2026, 9, 4): Decimal("4.0000"), date(2026, 9, 9): Decimal("4.2000")}
    )


def test_fx_cost_against_nbp_for_purchases_and_refunds(conn: sqlite3.Connection) -> None:
    seed_rates(conn)
    buy = add(
        conn, "-102.00", day="2026-09-07", account=2, orig_amount="-25.00", orig_currency="EUR"
    )
    back = add(
        conn,
        "39.00",
        "card_refund",
        day="2026-09-08",
        account=2,
        orig_amount="10.00",
        orig_currency="EUR",
    )
    add(conn, "-50.00", day="2026-09-08", account=2)  # PLN — bez kosztu
    c = hidden_costs.build(conn, *SEP)
    by_id = {i.txn_id: i for i in c.fx}
    assert by_id[buy].cost == Decimal("2.00")  # 102 − 25 × 4,0000 (tabela z 4.09)
    assert by_id[buy].pct == Decimal("2.0")
    assert by_id[back].cost == Decimal("1.00")  # bank oddał 39 zamiast 40
    assert c.fx_cost == Decimal("3.00") and c.missing == 0
    assert c.fx_volume == Decimal("140.00")  # wartość po kursie NBP
    assert c.fx_pct == Decimal("2.1")


def test_missing_rate_is_counted_not_guessed(conn: sqlite3.Connection) -> None:
    add(conn, "-102.00", day="2026-09-07", account=2, orig_amount="-25.00", orig_currency="CZK")
    c = hidden_costs.build(conn, *SEP)
    assert [i.cost for i in c.fx] == [None]
    assert c.fx_cost == Decimal("0") and c.missing == 1


def test_fees_sum_bank_charges_and_their_refunds(conn: sqlite3.Connection) -> None:
    add(conn, "-7.00", "fee", "OPLATA ZA KARTE", day="2026-09-05")
    add(conn, "7.00", "fee", "ZWROT OPLATY", day="2026-09-06")
    add(conn, "-2.99", "fee", "PROWIZJA", day="2026-09-20", account=2)
    add(conn, "-5.00", "fee", "PROWIZJA", day="2026-10-02")  # poza okresem
    add(conn, "-3.00", "fee", "PROWIZJA", day="2026-09-21", status="PDNG")  # oczekująca
    c = hidden_costs.build(conn, *SEP)
    assert c.fees == Decimal("2.99")
    assert c.total == c.fees + c.fx_cost


def test_months_split_costs_by_transaction_month(conn: sqlite3.Connection) -> None:
    seed_rates(conn)
    add(conn, "-102.00", day="2026-09-07", account=2, orig_amount="-25.00", orig_currency="EUR")
    add(conn, "-1.50", "fee", day="2026-08-10")
    c = hidden_costs.build(conn, date(2026, 8, 1), date(2026, 10, 1))
    months = hidden_costs.months(c, date(2026, 10, 1))
    assert [(m.start, m.fx_cost, m.fees) for m in months] == [
        (date(2026, 9, 1), Decimal("2.00"), Decimal("0")),
        (date(2026, 8, 1), Decimal("0"), Decimal("1.50")),
    ]


def test_csv_until_is_last_settle_date_of_card_csv() -> None:
    from budget import ledger
    from budget.storage import db

    from .test_ledger import CARD_NO, CUR_IBAN, account, card_row, csv_bytes

    c = db.connect(":memory:")
    with ledger.transaction(c):
        card = ledger.upsert_eb_account(
            c, account("u-card", "PL00999988887777666655554444", "Visa")
        )
        ledger.upsert_eb_account(c, account("u-cur", CUR_IBAN, "Konto"))
    assert hidden_costs.csv_until(c) is None
    rows = csv_bytes(
        card_row(CARD_NO, "2026-09-01", "2026-09-03", "SKLEP X , MIASTO A , 616", "-10.00"),
        card_row(CARD_NO, "2026-09-20", "2026-09-22", "SKLEP Y , MIASTO A , 616", "-20.00"),
    )
    ledger.ingest_csv(c, rows, card_map={CARD_NO: card})
    assert hidden_costs.csv_until(c) == date(2026, 9, 22)


def test_only_pln_amounts_count(conn: sqlite3.Connection) -> None:
    add(conn, "-7.00", "fee", "PROWIZJA", day="2026-09-05", currency="EUR")  # konto walutowe
    add(conn, "-1.00", "fee", "PROWIZJA", day="2026-09-05")
    assert hidden_costs.build(conn, *SEP).fees == Decimal("1.00")


def test_zero_foreign_amount_has_cost_but_no_pct(conn: sqlite3.Connection) -> None:
    seed_rates(conn)
    add(conn, "-3.00", day="2026-09-07", account=2, orig_amount="0.00", orig_currency="EUR")
    (item,) = hidden_costs.build(conn, *SEP).fx
    assert item.cost == Decimal("3.00") and item.pct is None
