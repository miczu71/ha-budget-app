"""Typ transakcji: taksonomia z „Rodzaju transakcji” Millenetu i heurystyka dla API.

API Millennium nie podaje typu (brak `bank_transaction_code` i MCC), więc dla transakcji
z API typ odtwarzamy z kształtu opisu i obecności kontrahenta (`kind_source = "heuristic"`);
import CSV nadpisuje go typem banku (`kind_source = "csv"`).
"""

from __future__ import annotations

import re
from decimal import Decimal
from enum import StrEnum

from budget.normalize import CARD_DESC_RE, fold


class Kind(StrEnum):
    CARD = "card"  # zakup kartą (stacjonarnie, internet, cykliczna)
    CARD_REFUND = "card_refund"
    BLIK = "blik"  # zakup BLIK
    BLIK_REFUND = "blik_refund"
    PHONE_TRANSFER = "phone_transfer"  # przelew na telefon (BLIK P2P), oba kierunki
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    STANDING_ORDER = "standing_order"
    DIRECT_DEBIT = "direct_debit"
    CASH = "cash"  # wypłata gotówki
    LOAN = "loan"  # rata kredytu
    CARD_REPAYMENT = "card_repayment"  # spłata karty kredytowej (obie strony)
    FEE = "fee"  # prowizje i opłaty banku
    OTHER = "other"


REFUND_KINDS = frozenset({Kind.CARD_REFUND, Kind.BLIK_REFUND})
PURCHASE_KINDS = frozenset({Kind.CARD, Kind.BLIK})

# „Rodzaj transakcji” z CSV (po `fold`) → typ
CSV_KINDS: dict[str, Kind] = {
    "ZAKUP - FIZ. UZYCIE KARTY": Kind.CARD,
    "ZAKUP - BEZ FIZ. UZYCIA KARTY": Kind.CARD,
    "PLATNOSC KARTA W INTERNECIE": Kind.CARD,
    "PLATNOSC CYKLICZNA KARTA": Kind.CARD,
    "ZAKUP - ZWROT": Kind.CARD_REFUND,
    "PLATNOSC KARTA W INTERNECIE ZWROT": Kind.CARD_REFUND,
    "PLATNOSC BLIK": Kind.BLIK,
    "PLATNOSC BLIK W INTERNECIE": Kind.BLIK,
    "PLATNOSC BLIK W INTERNECIE - ZWROT": Kind.BLIK_REFUND,
    "PRZELEW NA TELEFON": Kind.PHONE_TRANSFER,
    "PRZELEW PRZYCHODZACY": Kind.TRANSFER_IN,
    "PRZELEW WEWNETRZNY PRZYCHODZACY": Kind.TRANSFER_IN,
    "PRZELEW NATYCHMIASTOWY PRZYCHODZACY": Kind.TRANSFER_IN,
    "PRZELEW WEWNETRZNY WYCHODZACY": Kind.TRANSFER_OUT,
    "PRZELEW DO INNEGO BANKU": Kind.TRANSFER_OUT,
    "PLATNOSC INTERNETOWA WYCHODZACA": Kind.TRANSFER_OUT,
    "STALE ZLECENIE ZEWNETRZNE": Kind.STANDING_ORDER,
    "STALE ZLECENIE WEWNATRZ BANKU": Kind.STANDING_ORDER,
    "POLECENIE ZAPLATY": Kind.DIRECT_DEBIT,
    "WYPLATA BLIK Z BANKOMATU": Kind.CASH,
    "WYPLATA GOTOWKI": Kind.CASH,
    "WYPLATA GOTOWKOWA": Kind.CASH,
    "OPERACJE SO NA KREDYTACH": Kind.LOAN,
    "WCZESN.SPL.KARTY:": Kind.CARD_REPAYMENT,
    "PROWIZJA": Kind.FEE,
}

# Nieznane wartości (bank dodaje nowe) — wzorce w kolejności od najbardziej szczegółowych
_CSV_FALLBACK: tuple[tuple[re.Pattern[str], Kind], ...] = (
    (re.compile(r"SPL\.?KARTY"), Kind.CARD_REPAYMENT),
    (re.compile(r"BLIK.*ZWROT"), Kind.BLIK_REFUND),
    (re.compile(r"ZWROT"), Kind.CARD_REFUND),
    (re.compile(r"WYPLATA|BANKOMAT"), Kind.CASH),
    (re.compile(r"KARTA|KARTY|ZAKUP"), Kind.CARD),
    (re.compile(r"TELEFON"), Kind.PHONE_TRANSFER),
    (re.compile(r"BLIK"), Kind.BLIK),
    (re.compile(r"ZLECENIE"), Kind.STANDING_ORDER),
    (re.compile(r"POLECENIE"), Kind.DIRECT_DEBIT),
    (re.compile(r"PRZYCHODZ"), Kind.TRANSFER_IN),
    (re.compile(r"PRZELEW|WYCHODZ"), Kind.TRANSFER_OUT),
    (re.compile(r"KREDYT"), Kind.LOAN),
    (re.compile(r"PROWIZJA|OPLATA"), Kind.FEE),
)


def from_csv(value: str, amount: Decimal, *, card_account: bool, description: str = "") -> Kind:
    """Typ z kolumny „Rodzaj transakcji”. Wiersze karty kredytowej mają ją pustą."""
    key = fold(value)
    if not key:
        return _card_account_kind(description, amount) if card_account else Kind.OTHER
    if key in CSV_KINDS:
        return CSV_KINDS[key]
    for pattern, kind in _CSV_FALLBACK:
        if pattern.search(key):
            return kind
    return Kind.OTHER


def _card_account_kind(description: str, amount: Decimal) -> Kind:
    desc = fold(description)
    if desc.startswith("WCZESN.SPL"):
        return Kind.CARD_REPAYMENT
    if desc.startswith("OPLATA") or "PROWIZJA" in desc:
        return Kind.FEE
    return Kind.CARD_REFUND if amount > 0 else Kind.CARD


def from_api(
    description: str,
    amount: Decimal,
    *,
    card_account: bool,
    counterparty_name: str | None = None,
    counterparty_account: str | None = None,
) -> Kind:
    """Heurystyka typu z pól API Millennium (zob. `docs/FINDINGS_millennium.md`)."""
    if card_account:
        return _card_account_kind(description, amount)
    desc = fold(description)
    debit = amount < 0
    if not desc:
        # Spłata karty po stronie rachunku: pusty opis, brak kontrahenta
        return Kind.CARD_REPAYMENT if debit and not counterparty_name else Kind.OTHER
    if desc.startswith("WCZESN.SPL"):
        return Kind.CARD_REPAYMENT
    if "LOAN REPAYMENT" in desc or desc.startswith("SPLATA RATY"):
        return Kind.LOAN
    if desc.startswith("/OPT/"):
        return Kind.BLIK
    if desc.startswith("/OPF/"):
        return Kind.BLIK_REFUND
    if "NA TELEFON" in desc:
        return Kind.PHONE_TRANSFER
    if desc.startswith("BANKOMAT") and not counterparty_account:
        return Kind.CASH
    if CARD_DESC_RE.search(desc):
        if desc.startswith(("UL ", "UL.")):
            return Kind.CASH  # wypłata kartą w bankomacie: opis to sam adres
        return Kind.CARD if debit else Kind.CARD_REFUND
    if counterparty_account:
        return Kind.TRANSFER_OUT if debit else Kind.TRANSFER_IN
    if counterparty_name and debit:
        return Kind.BLIK  # płatność BLIK w punkcie: kontrahent bez numeru konta
    return Kind.OTHER
