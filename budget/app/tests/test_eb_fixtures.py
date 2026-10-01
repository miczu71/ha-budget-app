"""Modele na prawdziwych odpowiedziach Sandboxa EB (Mock ASPSP, dane syntetyczne z
`tools/make_mock_dataset.py`, pobrane `python -m budget.cli transactions` 2026-10-01)."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from budget.eb_models import SessionResponse, Transaction

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_session_fixture_parses() -> None:
    session = SessionResponse.from_api(_load("eb_mock_session.json"))
    assert len(session.accounts) == 3
    assert {a.currency for a in session.accounts} == {"PLN"}
    # Ten sam IBAN dwa razy w sesji → ten sam identification_hash (hash z IBAN + waluty),
    # więc identification_hash nie jest unikalny w obrębie sesji, uid jest.
    hashes = [a.identification_hash for a in session.accounts]
    assert hashes[0] == hashes[1] != hashes[2]
    assert len({a.uid for a in session.accounts}) == 3


def test_transactions_fixture_parses_and_balances() -> None:
    main = [
        Transaction.from_api(t) for t in _load("eb_mock_transactions_main.json")["transactions"]
    ]
    savings = [
        Transaction.from_api(t) for t in _load("eb_mock_transactions_savings.json")["transactions"]
    ]
    assert len(main) == 78 and len(savings) == 4
    assert sum(1 for t in main if t.status == "PDNG") == 1
    pending = next(t for t in main if t.status == "PDNG")
    assert pending.booking_date is None and pending.entry_reference is None

    # Saldo z zestawu (otwarcie 5000/20000 + transakcje BOOK) zgadza się z CLBD z Sandboxa
    booked = sum((t.signed_amount for t in main if t.status == "BOOK"), Decimal(0))
    assert Decimal("5000.00") + booked == Decimal("24295.69")
    assert Decimal("20000.00") + sum((t.signed_amount for t in savings), Decimal(0)) == Decimal(
        "26000.00"
    )

    # Przelewy własne: IBAN kontrahenta po jednej stronie = IBAN drugiego konta
    own = [t for t in main if t.counterparty_iban == "PL27114020040000300201355387"]
    assert len(own) == len(savings)
    assert all(t.signed_amount == Decimal("-1500.00") for t in own)

    # Bliźniacze transakcje bez identyfikatorów — przypadek dla deduplikacji z licznikiem (M2)
    twins = [t for t in main if t.counterparty_name == "AUTOMAT KAWA MPK"]
    assert len(twins) == 2 and twins[0].raw == twins[1].raw
