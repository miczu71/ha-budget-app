from decimal import Decimal

import pytest
from pydantic import ValidationError

from budget.eb_models import Amount, Transaction, TransactionsPage


def test_float_amount_rejected() -> None:
    with pytest.raises(ValidationError, match="float"):
        Amount.model_validate({"currency": "PLN", "amount": 12.3})


def test_debit_transaction_fields() -> None:
    data = {
        "transaction_id": "t1",
        "transaction_amount": {"currency": "PLN", "amount": "45.99"},
        "credit_debit_indicator": "DBIT",
        "status": "BOOK",
        "booking_date": "2026-09-15",
        "creditor": {"name": "BIEDRONKA 123"},
        "creditor_account": {"iban": "PL00111"},
        "debtor": {"name": "JAN"},
        "remittance_information": ["Zakup kartą ", "", " nr 1234"],
        "merchant_category_code": "5411",
        "unknown_field": 1,
    }
    t = Transaction.from_api(data)
    assert t.signed_amount == Decimal("-45.99")
    assert t.counterparty_name == "BIEDRONKA 123"
    assert t.counterparty_iban == "PL00111"
    assert t.description == "Zakup kartą nr 1234"
    assert t.raw == data
    assert "raw" not in t.model_dump()


def test_credit_counterparty_is_debtor() -> None:
    t = Transaction.from_api(
        {
            "transaction_amount": {"currency": "PLN", "amount": "1000.00"},
            "credit_debit_indicator": "CRDT",
            "status": "PDNG",
            "debtor": {"name": "PRACODAWCA SA"},
            "debtor_account": {"iban": "PL99"},
        }
    )
    assert t.signed_amount == Decimal("1000.00")
    assert t.counterparty_name == "PRACODAWCA SA"
    assert t.counterparty_iban == "PL99"


def test_page_without_key() -> None:
    page = TransactionsPage.from_api({"transactions": [], "continuation_key": None})
    assert page.continuation_key is None
