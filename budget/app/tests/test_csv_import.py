from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from budget import csv_import
from budget.csv_import import CsvFormatError, collapse, parse, unwrap
from budget.kinds import Kind

FIXTURE = Path(__file__).parent / "fixtures" / "millenet_sample.csv"
HEADER = (
    '"Numer rachunku/karty","Data transakcji","Data rozliczenia","Rodzaj transakcji",'
    '"Na konto/Z konta","Odbiorca/Zleceniodawca","Opis","Obciążenia","Uznania","Saldo","Waluta"'
)
IBAN = "PL00 1111 2222 3333 4444 5555 6666"
CARD = "1234 XXXX XXXX 5678"


def make(*rows: str) -> bytes:
    return ("﻿" + "\r\n".join([HEADER, *rows]) + "\r\n").encode()


def row(*fields: str) -> str:
    return ",".join(f'"{f}"' for f in fields)


def test_fixture_parses() -> None:
    result = parse(FIXTURE.read_bytes())
    numbers = csv_import.numbers(result.rows)
    assert len(numbers) == 3
    assert sum(1 for n in numbers if n.startswith("PL")) == 1
    # wiersze karty bez kwoty (opłata 0) są pomijane, nie psują importu
    assert all(reason == "brak kwoty" for _, reason in result.skipped)
    assert len(result.skipped) == 2


def test_fixture_balance_is_continuous() -> None:
    rows = [r for r in parse(FIXTURE.read_bytes()).rows if not r.is_card]
    assert rows and csv_import.balance_breaks(rows) == []


def test_fixture_card_blocks_collapse() -> None:
    rows = [r for r in parse(FIXTURE.read_bytes()).rows if r.is_card]
    by_number: dict[str, list[csv_import.CsvRow]] = {}
    for r in rows:
        by_number.setdefault(r.number, []).append(r)
    assert len(by_number) == 2
    collapsed = collapse(by_number)
    assert len(collapsed) == len(rows) // 2


def test_header_is_validated() -> None:
    with pytest.raises(CsvFormatError):
        parse(b'"a","b"\r\n"1","2"\r\n')


def test_unwrap() -> None:
    seg44 = "A" * 43 + "B"  # 44 znaki: Millenet zjadł spację po segmencie
    seg45 = "C" * 45
    assert unwrap(f"{seg44}\xa0DALEJ") == f"{seg44} DALEJ"
    assert unwrap(f"{seg45}\xa0DALEJ") == f"{seg45}DALEJ"


def test_account_card_payment_row() -> None:
    desc = "LIDL UL. TESTOWA 5 TESTOWO POL\xa02026-09-29"
    data = make(
        row(
            IBAN,
            "2026-09-30",
            "2026-09-30",
            "ZAKUP - FIZ. UŻYCIE KARTY",
            "",
            "",
            desc,
            "-12.30",
            "",
            "100.00",
            "PLN",
        ),
    )
    (r,) = parse(data).rows
    assert r.number == IBAN.replace(" ", "")
    assert not r.is_card
    assert r.kind is Kind.CARD
    assert r.amount == Decimal("-12.30")
    assert r.balance_after == Decimal("100.00")
    assert r.description == "LIDL UL. TESTOWA 5 TESTOWO POL 2026-09-29"


def test_transfer_row_counterparty() -> None:
    data = make(
        row(
            IBAN,
            "2026-09-01",
            "2026-09-01",
            "PRZELEW PRZYCHODZĄCY",
            "11 2222 3333 4444 5555 6666 7777",
            "FIRMA\xa0UL. TESTOWA 1\xa000-000 TESTOWO",
            "WYNAGRODZENIE",
            "",
            "5000.00",
            "6000.00",
            "PLN",
        ),
    )
    (r,) = parse(data).rows
    assert r.kind is Kind.TRANSFER_IN
    assert r.counterparty_name == "FIRMA"
    assert r.counterparty_account == "PL11222233334444555566667777"


def test_card_row_with_foreign_currency() -> None:
    desc = "SKLEP TESTOWY 001        , TESTOWO 5    , 380 -10.0 EUR"
    data = make(row(CARD, "2026-07-24", "2026-07-26", "", "", "", desc, "-43.21", "", "", "PLN"))
    (r,) = parse(data).rows
    assert r.is_card
    assert r.kind is Kind.CARD
    assert r.tx_date == date(2026, 7, 24)
    assert r.settle_date == date(2026, 7, 26)
    assert r.balance_after is None
    assert r.orig_amount == Decimal("-10.00")
    assert r.orig_currency == "EUR"
    assert r.description == "SKLEP TESTOWY 001 TESTOWO 5"


def test_collapse_keeps_real_twins() -> None:
    desc = "SKLEP , TESTOWO , 616"
    twin = row(CARD, "2026-07-01", "2026-07-02", "", "", "", desc, "-5.00", "", "", "PLN")
    other = twin.replace("1234 XXXX XXXX 5678", "9999 XXXX XXXX 0000")
    # karta główna: dwa identyczne zakupy; dodatkowa: tylko jeden z nich
    rows = parse(make(twin, twin, other)).rows
    by_number: dict[str, list[csv_import.CsvRow]] = {}
    for r in rows:
        by_number.setdefault(r.number, []).append(r)
    collapsed = collapse(by_number)
    assert [r.occurrence for r in collapsed] == [0, 1]


def test_balance_break_detected() -> None:
    data = make(
        row(IBAN, "2026-09-02", "2026-09-02", "PROWIZJA", "", "", "X", "-1.00", "", "98.00", "PLN"),
        row(
            IBAN, "2026-09-01", "2026-09-01", "PROWIZJA", "", "", "Y", "-1.00", "", "100.00", "PLN"
        ),
    )
    assert csv_import.balance_breaks(parse(data).rows) == [(2, Decimal("1.00"))]
