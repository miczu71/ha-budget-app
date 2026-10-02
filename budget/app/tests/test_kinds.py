from decimal import Decimal

import pytest

from budget.kinds import CSV_KINDS, Kind, from_api, from_csv

D = Decimal("-10.00")
C = Decimal("10.00")


def test_csv_known_values() -> None:
    assert from_csv("WCZEŚN.SPŁ.KARTY:", D, card_account=False) is Kind.CARD_REPAYMENT
    assert from_csv("PŁATNOŚĆ BLIK W INTERNECIE - ZWROT", C, card_account=False) is (
        Kind.BLIK_REFUND
    )
    assert from_csv("ZAKUP - FIZ. UŻYCIE KARTY", D, card_account=False) is Kind.CARD
    assert len(CSV_KINDS) == 25


def test_csv_unknown_value_uses_patterns() -> None:
    assert from_csv("PRZELEW EKSPRESOWY PRZYCHODZĄCY", C, card_account=False) is Kind.TRANSFER_IN
    assert from_csv("COŚ ZUPEŁNIE NOWEGO", D, card_account=False) is Kind.OTHER


def test_csv_card_rows_have_empty_kind() -> None:
    assert from_csv("", D, card_account=True, description="SKLEP , X , 616") is Kind.CARD
    assert from_csv("", C, card_account=True, description="SKLEP , X , 616") is Kind.CARD_REFUND
    fee = "OPŁATA MIESIĘCZNA ZA OBSLUGĘ KARTY, 616"
    assert from_csv("", D, card_account=True, description=fee) is Kind.FEE


@pytest.mark.parametrize(
    ("desc", "amount", "name", "account", "expected"),
    [
        ("", D, None, None, Kind.CARD_REPAYMENT),
        ("INSTALLMENT LOAN REPAYMENT", D, None, None, Kind.LOAN),
        ("/OPT/X///// BPID:AB12 PayU S.A.", D, "sklep.example.pl", None, Kind.BLIK),
        ("/OPF/X///// ab12 PayPro S.A.", C, "sklep.example.pl", None, Kind.BLIK_REFUND),
        ("Przelew BLIK na telefon", D, "OSOBA", "PL001", Kind.PHONE_TRANSFER),
        ("Bankomat Euronet UL TESTOWA 1 00-000 Testowo", D, "OSOBA", None, Kind.CASH),
        ("LIDL UL. TESTOWA 5 TESTOWO POL 2026-09-29", D, None, None, Kind.CARD),
        ("Allegro  Poznan POL 2026-08-27", C, "OSOBA", "PL001", Kind.CARD_REFUND),
        ("ul. Testowa 58  Testowo POL 2026-09-01", D, None, None, Kind.CASH),
        ("Wynagrodzenie", C, "FIRMA", "PL001", Kind.TRANSFER_IN),
        ("Czynsz", D, "WSPÓLNOTA", "PL001", Kind.TRANSFER_OUT),
        ("Kebab 123", D, "Kebab 123", None, Kind.BLIK),
    ],
)
def test_api_heuristic_current_account(
    desc: str, amount: Decimal, name: str | None, account: str | None, expected: Kind
) -> None:
    got = from_api(
        desc, amount, card_account=False, counterparty_name=name, counterparty_account=account
    )
    assert got is expected


def test_api_heuristic_card_account() -> None:
    assert from_api("WCZESN.SPL.Z RACHUNKU: 123", C, card_account=True) is Kind.CARD_REPAYMENT
    assert from_api("Sklep Testowy    ", D, card_account=True) is Kind.CARD
    assert from_api("Sklep Testowy    ", C, card_account=True) is Kind.CARD_REFUND
