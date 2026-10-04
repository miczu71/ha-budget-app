"""Księga na danych syntetycznych: L0–L4, kolejność importów, uzgodnienie salda."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from budget import eb_ingest, ledger
from budget.eb_models import Account, Balance, Transaction
from budget.storage import db

CUR_IBAN = "PL00111122223333444455556666"
CARD_IBAN = "PL00999988887777666655554444"
CARD_NO = "1234XXXXXXXX5678"
CARD_NO_2 = "9999XXXXXXXX0000"
FIXTURE = Path(__file__).parent / "fixtures" / "millenet_sample.csv"
HEADER = (
    '"Numer rachunku/karty","Data transakcji","Data rozliczenia","Rodzaj transakcji",'
    '"Na konto/Z konta","Odbiorca/Zleceniodawca","Opis","Obciążenia","Uznania","Saldo","Waluta"'
)


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = db.connect(":memory:")
    yield c
    c.close()


def account(uid: str, iban: str, product: str) -> Account:
    return Account.from_api(
        {
            "uid": uid,
            "identification_hash": f"hash-{uid}",
            "account_id": {"iban": iban},
            "currency": "PLN",
            "product": product,
        }
    )


@pytest.fixture
def accounts(conn: sqlite3.Connection) -> tuple[int, int]:
    with ledger.transaction(conn):
        cur = ledger.upsert_eb_account(conn, account("u-cur", CUR_IBAN, "Konto Testowe"))
        card = ledger.upsert_eb_account(conn, account("u-card", CARD_IBAN, "Visa Testowa"))
    return cur, card


def tx(
    ref: str | None,
    day: str,
    amount: str,
    desc: str = "",
    *,
    status: str = "BOOK",
    creditor: str | None = None,
    creditor_iban: str | None = None,
) -> Transaction:
    value = Decimal(amount)
    data: dict[str, Any] = {
        "entry_reference": ref,
        "transaction_amount": {"currency": "PLN", "amount": str(abs(value))},
        "credit_debit_indicator": "CRDT" if value > 0 else "DBIT",
        "status": status,
        "booking_date": day if status == "BOOK" else None,
        # Millennium nie podaje transaction_date dla zaksięgowanych (data jest w opisie)
        "transaction_date": day if status == "PDNG" else None,
        "remittance_information": [desc] if desc else [],
    }
    if creditor:
        data["creditor"] = {"name": creditor}
    if creditor_iban:
        data["creditor_account"] = {"iban": creditor_iban}
    return Transaction.from_api(data)


def api(
    conn: sqlite3.Connection,
    account_id: int,
    txns: list[Transaction],
    *,
    card: bool = False,
    at: str = "2026-10-01T12:00:00+00:00",
) -> ledger.ImportStats:
    converted = eb_ingest.convert(txns, card_account=card)
    return ledger.ingest_api(conn, account_id, converted, fetched_at=at)


def csv_bytes(*rows: tuple[str, ...]) -> bytes:
    lines = [HEADER, *(",".join(f'"{f}"' for f in r) for r in rows)]
    return ("﻿" + "\r\n".join(lines) + "\r\n").encode()


def cur_row(day: str, kind: str, desc: str, amount: str, balance: str) -> tuple[str, ...]:
    debit, credit = (amount, "") if amount.startswith("-") else ("", amount)
    return (CUR_IBAN, day, day, kind, "", "", desc, debit, credit, balance, "PLN")


def card_row(number: str, tx_day: str, settle: str, desc: str, amount: str) -> tuple[str, ...]:
    debit, credit = (amount, "") if amount.startswith("-") else ("", amount)
    return (number, tx_day, settle, "", "", "", desc, debit, credit, "", "PLN")


def txns(conn: sqlite3.Connection, account_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM txn WHERE account_id = ? ORDER BY booking_date, id", (account_id,)
    ).fetchall()


# --- API (L0) ---------------------------------------------------------------------------------


def test_api_reimport_changes_nothing(conn: sqlite3.Connection, accounts: tuple[int, int]) -> None:
    cur, _ = accounts
    batch = [tx("R|1", "2026-09-01", "-10.00", "A"), tx("R|2", "2026-09-01", "25.00", "B")]
    first = api(conn, cur, batch)
    again = api(conn, cur, batch)
    assert (first.new, first.updated) == (2, 0)
    assert (again.new, again.updated) == (0, 0)
    assert len(txns(conn, cur)) == 2


def test_api_twins_same_day_stay_separate(
    conn: sqlite3.Connection, accounts: tuple[int, int]
) -> None:
    cur, _ = accounts
    batch = [tx("R|1", "2026-09-01", "-5.00", "KAWA"), tx("R|2", "2026-09-01", "-5.00", "KAWA")]
    api(conn, cur, batch)
    rows = txns(conn, cur)
    assert [r["occurrence"] for r in rows] == [0, 1]


def test_api_renumbered_reference_is_alias(
    conn: sqlite3.Connection, accounts: tuple[int, int]
) -> None:
    cur, _ = accounts
    api(conn, cur, [tx("R|2026-09-01|1", "2026-09-01", "-10.00", "SKLEP")])
    stats = api(conn, cur, [tx("R|2026-09-01|7", "2026-09-01", "-10.00", "SKLEP")])
    assert stats.new == 0
    (row,) = txns(conn, cur)
    refs = conn.execute("SELECT ref FROM txn_ref WHERE txn_id = ?", (row["id"],)).fetchall()
    assert sorted(r["ref"] for r in refs) == ["R|2026-09-01|1", "R|2026-09-01|7"]


def test_pending_replaced_by_booked(conn: sqlite3.Connection, accounts: tuple[int, int]) -> None:
    cur, _ = accounts
    api(conn, cur, [tx(None, "2026-09-01", "-9.99", "BLOKADA SKLEP", status="PDNG")])
    assert [r["status"] for r in txns(conn, cur)] == ["PDNG"]
    api(conn, cur, [tx("R|1", "2026-09-02", "-9.99", "SKLEP")])
    assert [r["status"] for r in txns(conn, cur)] == ["BOOK"]


def test_api_kind_heuristic(conn: sqlite3.Connection, accounts: tuple[int, int]) -> None:
    cur, _ = accounts
    api(conn, cur, [tx("R|1", "2026-09-01", "-12.00", "LIDL UL. TESTOWA TESTOWO POL 2026-08-30")])
    (row,) = txns(conn, cur)
    assert (row["kind"], row["kind_source"], row["tx_date"]) == ("card", "heuristic", "2026-08-30")


# --- CSV (L0, L1) ------------------------------------------------------------------------------


def test_csv_fixture_without_api(conn: sqlite3.Connection) -> None:
    stats = ledger.ingest_csv(conn, FIXTURE.read_bytes())
    assert stats.new == stats.total
    # rachunek założony z IBAN-u, numery kart czekają na mapowanie
    statuses = dict(conn.execute("SELECT status, count(*) FROM csv_row GROUP BY 1").fetchall())
    assert statuses["inserted"] > 0 and statuses["unmapped"] == 10
    again = ledger.ingest_csv(conn, FIXTURE.read_bytes())
    assert again.new == 0


def test_csv_fixture_card_duplicates_collapse_with_manual_map(conn: sqlite3.Connection) -> None:
    with ledger.transaction(conn):
        card = ledger.upsert_eb_account(conn, account("u-card", CARD_IBAN, "Visa Testowa"))
    numbers = {"4293 XXXX XXXX 5575": card, "9183 XXXX XXXX 6236": card}
    ledger.ingest_csv(conn, FIXTURE.read_bytes(), card_map=numbers)
    statuses = dict(
        conn.execute(
            "SELECT status, count(*) FROM csv_row WHERE number NOT LIKE 'PL%' GROUP BY 1"
        ).fetchall()
    )
    assert statuses == {"inserted": 5, "duplicate": 5}
    assert len(txns(conn, card)) == 5


def test_csv_before_boundary_inserted_inside_enriches(
    conn: sqlite3.Connection, accounts: tuple[int, int]
) -> None:
    cur, _ = accounts
    api(
        conn,
        cur,
        [
            tx("R|1", "2026-09-10", "-20.00", "ZAKUP X"),
            tx("R|2", "2026-09-11", "-30.00", "PRZELEW", creditor="FIRMA", creditor_iban=None),
        ],
    )
    data = csv_bytes(
        cur_row("2026-09-11", "PRZELEW DO INNEGO BANKU", "PRZELEW", "-30.00", "50.00"),
        cur_row("2026-09-10", "ZAKUP - FIZ. UŻYCIE KARTY", "ZAKUP X", "-20.00", "80.00"),
        cur_row("2026-09-05", "PROWIZJA", "OPŁATA", "-1.00", "100.00"),
    )
    ledger.ingest_csv(conn, data)
    rows = txns(conn, cur)
    assert [(r["booking_date"], r["source"], r["kind"]) for r in rows] == [
        ("2026-09-05", "csv", "fee"),
        ("2026-09-10", "eb", "card"),
        ("2026-09-11", "eb", "transfer_out"),
    ]
    assert rows[2]["kind_source"] == "csv"
    assert rows[2]["balance_after"] == "50.00"


def _ledger_digest(conn: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return sorted(
        tuple(r)
        for r in conn.execute(
            "SELECT account_id, booking_date, amount, kind, source, balance_after, "
            "transfer_group IS NOT NULL, refund_of IS NOT NULL FROM txn"
        )
    )


def test_import_order_does_not_matter(tmp_path: Path) -> None:
    api_batch = [
        tx("R|1", "2026-09-10", "-20.00", "ZAKUP X"),
        tx("R|2", "2026-09-12", "-15.00", "ZAKUP Y"),
    ]
    data = csv_bytes(
        cur_row("2026-09-12", "ZAKUP - FIZ. UŻYCIE KARTY", "ZAKUP Y", "-15.00", "65.00"),
        cur_row("2026-09-10", "ZAKUP - FIZ. UŻYCIE KARTY", "ZAKUP X", "-20.00", "80.00"),
        cur_row("2026-09-01", "PRZELEW PRZYCHODZĄCY", "WPŁATA", "100.00", "100.00"),
    )
    digests = []
    for order in ("api-csv", "csv-api"):
        c = db.connect(tmp_path / f"{order}.db")
        with ledger.transaction(c):
            cur = ledger.upsert_eb_account(c, account("u-cur", CUR_IBAN, "Konto"))
        if order == "api-csv":
            api(c, cur, api_batch)
            ledger.ingest_csv(c, data)
        else:
            ledger.ingest_csv(c, data)
            api(c, cur, api_batch)
        digests.append(_ledger_digest(c))
        assert len(digests[-1]) == 3
    assert digests[0] == digests[1]


def test_card_fuzzy_match_only_for_foreign_currency(
    conn: sqlite3.Connection, accounts: tuple[int, int]
) -> None:
    _, card = accounts
    api(
        conn,
        card,
        [
            tx("C1", "2026-09-01", "-100.00", "TRATTORIA TESTOWA"),
            tx("C2", "2026-09-03", "-41.00", "TRATTORIA TESTOWA"),
            tx("C3", "2026-09-04", "-50.00", "SKLEP TESTOWY"),
        ],
        card=True,
    )
    data = csv_bytes(
        card_row(
            CARD_NO, "2026-08-30", "2026-09-01", "TRATTORIA TESTOWA , MIASTO , 380", "-100.00"
        ),
        card_row(
            CARD_NO,
            "2026-09-01",
            "2026-09-03",
            "TRATTORIA TESTOWA , MIASTO , 380 -9.5 EUR",
            "-42.00",
        ),
        # kwota PLN inna, ale bez waluty obcej → bez dopasowania rozmytego
        card_row(CARD_NO, "2026-09-02", "2026-09-04", "SKLEP TESTOWY , MIASTO , 616", "-51.00"),
    )
    ledger.ingest_csv(conn, data)  # numer karty mapuje się sam? nie — tylko 1 dokładna para
    assert conn.execute("SELECT count(*) FROM csv_row WHERE status = 'unmapped'").fetchone()[0]
    ledger.ingest_csv(conn, data, card_map={CARD_NO: card})
    statuses = [
        r["status"] for r in conn.execute("SELECT status FROM csv_row ORDER BY settle_date")
    ]
    assert statuses == ["enriched", "enriched", "unmatched"]
    fx = conn.execute("SELECT * FROM txn WHERE amount = '-41.00'").fetchone()
    assert (fx["orig_amount"], fx["orig_currency"]) == ("-9.50", "EUR")
    assert len(txns(conn, card)) == 3  # niesparowany wiersz CSV nie wchodzi do księgi


def test_card_number_auto_mapped_after_three_matches(
    conn: sqlite3.Connection, accounts: tuple[int, int]
) -> None:
    _, card = accounts
    days = ["2026-09-01", "2026-09-02", "2026-09-03"]
    api(
        conn, card, [tx(f"C{i}", d, f"-{i + 1}.00", "SKLEP") for i, d in enumerate(days)], card=True
    )
    rows = [
        card_row(CARD_NO, d, d, "SKLEP , MIASTO , 616", f"-{i + 1}.00") for i, d in enumerate(days)
    ]
    ledger.ingest_csv(conn, csv_bytes(*rows))
    assert ledger.account_by_alias(conn, "csv_number", CARD_NO) == card


# --- L2, L3 -----------------------------------------------------------------------------------


def test_card_repayment_pairs_across_accounts(
    conn: sqlite3.Connection, accounts: tuple[int, int]
) -> None:
    cur, card = accounts
    api(conn, cur, [tx("R|1", "2026-09-10", "-800.00"), tx("R|2", "2026-08-01", "-300.00")])
    api(conn, card, [tx("C1", "2026-09-11", "800.00", "WCZESN.SPL.Z RACHUNKU: 123")], card=True)
    paired = conn.execute(
        "SELECT transfer_group, count(*) AS n FROM txn WHERE amount IN ('-800.00', '800.00') "
        "GROUP BY 1"
    ).fetchall()
    assert len(paired) == 1 and paired[0]["n"] == 2
    # spłata bez pary (karta poza oknem danych) też jest przelewem
    solo = conn.execute("SELECT transfer_group FROM txn WHERE amount = '-300.00'").fetchone()
    assert solo["transfer_group"] is not None


def test_transfer_to_own_iban_but_same_account_is_not_transfer(
    conn: sqlite3.Connection, accounts: tuple[int, int]
) -> None:
    cur, _ = accounts
    api(
        conn,
        cur,
        [tx("R|1", "2026-09-10", "-100.00", "Bankomat Test", creditor="X", creditor_iban=CUR_IBAN)],
    )
    (row,) = txns(conn, cur)
    assert row["transfer_group"] is None


def test_refund_links_to_purchase(conn: sqlite3.Connection, accounts: tuple[int, int]) -> None:
    _, card = accounts
    api(
        conn,
        card,
        [
            tx("C1", "2026-08-01", "-200.00", "ZALANDO SE"),
            tx("C2", "2026-08-20", "150.00", "Zalando Payments GmbH"),
            tx("C3", "2026-08-21", "500.00", "Zalando Payments GmbH"),  # większy niż zakup
        ],
        card=True,
    )
    rows = {r["amount"]: r for r in txns(conn, card)}
    assert rows["150.00"]["refund_of"] == rows["-200.00"]["id"]
    assert rows["500.00"]["refund_of"] is None


# --- uzgodnienie salda --------------------------------------------------------------------------


def test_balance_check_csv_and_snapshot(
    conn: sqlite3.Connection, accounts: tuple[int, int]
) -> None:
    cur, _ = accounts
    api(conn, cur, [tx("R|1", "2026-09-10", "-20.00", "ZAKUP X")], at="2026-09-10T20:00:00+00:00")
    ledger.ingest_csv(
        conn,
        csv_bytes(
            cur_row("2026-09-10", "ZAKUP - FIZ. UŻYCIE KARTY", "ZAKUP X", "-20.00", "80.00"),
            cur_row("2026-09-01", "PRZELEW PRZYCHODZĄCY", "WPŁATA", "100.00", "100.00"),
        ),
    )
    snapshot = Balance.from_api(
        {"balance_amount": {"currency": "PLN", "amount": "80.00"}, "balance_type": "ITBD"}
    )
    ledger.ingest_balances(conn, cur, [snapshot], fetched_at="2026-09-10T20:00:30+00:00")
    # transakcja pobrana po migawce nie wchodzi do jej sumy
    api(conn, cur, [tx("R|2", "2026-09-11", "-5.00", "ZAKUP Z")], at="2026-09-11T08:00:00+00:00")
    check = next(c for c in ledger.check_balances(conn) if c.account_id == cur)
    assert check.days_checked == 2
    assert check.day_mismatches == []
    assert check.snapshot_checks == [
        ("2026-09-10T20:00:30+00:00", Decimal("80.00"), Decimal("80.00"))
    ]
    assert check.ok


def test_balance_check_detects_missing_transaction(
    conn: sqlite3.Connection, accounts: tuple[int, int]
) -> None:
    cur, _ = accounts
    ledger.ingest_csv(
        conn,
        csv_bytes(
            cur_row("2026-09-10", "PROWIZJA", "B", "-20.00", "70.00"),  # saldo „zgubiło” 10 zł
            cur_row("2026-09-01", "PRZELEW PRZYCHODZĄCY", "A", "100.00", "100.00"),
        ),
    )
    check = next(c for c in ledger.check_balances(conn) if c.account_id == cur)
    assert check.day_mismatches == [("2026-09-10", Decimal("10.00"))]
    assert not check.ok


def test_mock_dataset_without_references_is_idempotent(
    conn: sqlite3.Connection, accounts: tuple[int, int]
) -> None:
    import json

    cur, _ = accounts
    data = json.loads((FIXTURE.parent / "eb_mock_transactions_main.json").read_text("utf-8"))
    raw = [Transaction.from_api(t) for t in data["transactions"]]
    first = api(conn, cur, raw)
    again = api(conn, cur, raw)
    assert first.new == len([t for t in raw if t.status == "BOOK"])
    assert (again.new, again.updated) == (0, 0)


def _itbd(conn: sqlite3.Connection, account_id: int, amount: str, at: str) -> None:
    b = Balance.from_api(
        {"balance_amount": {"currency": "PLN", "amount": amount}, "balance_type": "ITBD"}
    )
    ledger.ingest_balances(conn, account_id, [b], fetched_at=at)


def _card_check(conn: sqlite3.Connection, card: int) -> ledger.BalanceCheck:
    return next(c for c in ledger.check_balances(conn) if c.account_id == card)


def test_card_check_uses_debt_sign_and_marks_pending_in_transit(
    conn: sqlite3.Connection, accounts: tuple[int, int]
) -> None:
    _, card = accounts
    _itbd(conn, card, "0.00", "2026-10-01T07:00:00+00:00")
    # autoryzacja: zadłużenie rośnie, w API transakcji jeszcze nie ma
    _itbd(conn, card, "50.00", "2026-10-01T19:00:00+00:00")
    check = _card_check(conn, card)
    assert check.delta_mode and check.status == "W DRODZE" and check.ok
    # po zaksięgowaniu: zakup −50 w księdze = zadłużenie +50
    api(
        conn,
        card,
        [tx("C1", "2026-10-02", "-50.00", "SKLEP")],
        card=True,
        at="2026-10-02T07:00:00+00:00",
    )
    _itbd(conn, card, "50.00", "2026-10-02T07:00:30+00:00")
    check = _card_check(conn, card)
    assert check.snapshot_checks[-1][1:] == (Decimal("50.00"), Decimal("50.00"))
    assert check.status == "OK" and check.ok
    # zwrot w księdze i w zadłużeniu w tym samym pobraniu → dalej OK
    api(
        conn,
        card,
        [tx("C2", "2026-10-03", "20.00", "SKLEP")],
        card=True,
        at="2026-10-03T07:00:00+00:00",
    )
    _itbd(conn, card, "30.00", "2026-10-03T07:00:30+00:00")
    assert _card_check(conn, card).status == "OK"


def test_card_difference_older_than_transit_window_is_mismatch(
    conn: sqlite3.Connection, accounts: tuple[int, int]
) -> None:
    _, card = accounts
    _itbd(conn, card, "0.00", "2026-10-01T07:00:00+00:00")
    _itbd(conn, card, "50.00", "2026-10-01T19:00:00+00:00")
    _itbd(conn, card, "50.00", "2026-10-03T19:00:00+00:00")
    assert _card_check(conn, card).status == "W DRODZE"
    _itbd(conn, card, "50.00", "2026-10-04T19:00:00+00:00")  # 3 dni bez transakcji w API
    check = _card_check(conn, card)
    assert check.status == "ROZBIEŻNOŚĆ" and not check.ok


def test_card_check_base_snapshot(conn: sqlite3.Connection, accounts: tuple[int, int]) -> None:
    _, card = accounts
    # pierwsza migawka złapana „w drodze”: autoryzacja w ITBD, zwrot już w API
    api(
        conn,
        card,
        [tx("C0", "2026-09-30", "100.00", "ZWROT")],
        card=True,
        at="2026-10-02T07:14:00+00:00",
    )
    _itbd(conn, card, "476.00", "2026-10-02T07:14:30+00:00")
    api(
        conn,
        card,
        [tx("C1", "2026-10-03", "-476.00", "SKLEP")],
        card=True,
        at="2026-10-02T19:30:00+00:00",
    )
    _itbd(conn, card, "377.67", "2026-10-02T19:30:30+00:00")
    _itbd(conn, card, "377.67", "2026-10-06T19:30:30+00:00")
    assert _card_check(conn, card).status == "ROZBIEŻNOŚĆ"
    assert ledger.set_reconcile_base(conn, card) == "2026-10-06T19:30:30+00:00"
    check = _card_check(conn, card)
    assert check.status == "OK" and check.base_at == "2026-10-06T19:30:30+00:00"
    _itbd(conn, card, "377.67", "2026-10-07T19:30:30+00:00")
    assert _card_check(conn, card).status == "OK"
