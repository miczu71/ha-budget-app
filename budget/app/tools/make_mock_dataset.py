"""Syntetyczny zbiór danych do Mock ASPSP (Sandbox Enable Banking) — w stylu polskiego konta.

Format pliku jak w przykładzie EB (`sample-data/DK-Danske_Bank-synthetic-1.json`):
`{"accounts": [{"info": {...}, "transactions": [...], "balances": [...]}]}`.
Wszystkie dane są fikcyjne. Zawiera przypadki brzegowe potrzebne w M2–M4:
MCC, BLIK bez MCC, wypłata, przelewy własne (obie strony), PDNG, dwie identyczne
transakcje tego samego dnia bez identyfikatorów, transakcja z `transaction_id`.

Użycie: python tools/make_mock_dataset.py --today 2026-10-01 --out mock.json
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

MAIN_IBAN = "PL61109010140000071219812874"
SAVINGS_IBAN = "PL27114020040000300201355387"
EMPLOYER_IBAN = "PL83101010230000261395100000"
TAURON_IBAN = "PL10105000997603123456789123"

CARD = {"code": "CustomerCardTransactions", "sub_code": "DebitCardPayment", "description": None}
TRANSFER = {
    "code": "IssuedCreditTransfers",
    "sub_code": "DomesticCreditTransfer",
    "description": None,
}
RECEIVED = {
    "code": "ReceivedCreditTransfers",
    "sub_code": "DomesticCreditTransfer",
    "description": None,
}
BLIK = {"code": "IssuedCreditTransfers", "sub_code": "MobilePayment", "description": None}

SHOPS = [
    ("BIEDRONKA 1234 WROCLAW", "5411", (25, 180)),
    ("LIDL WROCLAW KRZYKI", "5411", (40, 260)),
    ("ORLEN STACJA NR 4021", "5541", (150, 320)),
    ("RESTAURACJA PIEROGARNIA", "5812", (60, 190)),
    ("ROSSMANN 112", "5912", (20, 90)),
    ("SPOTIFY P1A2B3C4", "5815", (23.99, 23.99)),
]


def _amount(rng: random.Random, lo: float, hi: float) -> str:
    return str(Decimal(str(round(rng.uniform(lo, hi), 2))).quantize(Decimal("0.01")))


def _txn(
    *,
    ref: str | None,
    amount: str,
    indicator: str,
    booked: date | None,
    status: str = "BOOK",
    creditor: str | None = None,
    debtor: str | None = None,
    creditor_iban: str | None = None,
    debtor_iban: str | None = None,
    remittance: list[str],
    mcc: str | None = None,
    btc: dict[str, Any] | None = None,
    transaction_id: str | None = None,
    tx_date: date | None = None,
) -> dict[str, Any]:
    return {
        "entry_reference": ref,
        "transaction_id": transaction_id,
        "merchant_category_code": mcc,
        "transaction_amount": {"currency": "PLN", "amount": amount},
        "creditor": {"name": creditor} if creditor else None,
        "creditor_account": {"iban": creditor_iban} if creditor_iban else None,
        "debtor": {"name": debtor} if debtor else None,
        "debtor_account": {"iban": debtor_iban} if debtor_iban else None,
        "bank_transaction_code": btc,
        "credit_debit_indicator": indicator,
        "status": status,
        "booking_date": booked.isoformat() if booked else None,
        "value_date": booked.isoformat() if booked else None,
        "transaction_date": (tx_date or booked or date.today()).isoformat(),
        "balance_after_transaction": None,
        "reference_number": None,
        "remittance_information": remittance,
    }


def build(today: date, seed: int = 71) -> dict[str, Any]:
    rng = random.Random(seed)
    main: list[dict[str, Any]] = []
    savings: list[dict[str, Any]] = []
    n = 0

    def ref() -> str:
        nonlocal n
        n += 1
        return f"MCK{n:06d}"

    start = today - timedelta(days=120)
    day = start
    while day < today:
        # Zakupy kartą co 1–3 dni
        name, mcc, (lo, hi) = rng.choice(SHOPS)
        main.append(
            _txn(
                ref=ref(),
                amount=_amount(rng, lo, hi),
                indicator="DBIT",
                booked=day + timedelta(days=1),
                tx_date=day,
                creditor=name,
                remittance=[f"Płatność kartą {day:%d.%m.%Y} {name}"],
                mcc=mcc,
                btc=CARD,
            )
        )
        day += timedelta(days=rng.randint(1, 3))

    # Zdarzenia comiesięczne — każdy dzień okresu, żeby żaden miesiąc ich nie pominął
    day = start
    while day < today:
        if day.day == 10:  # wypłata
            main.append(
                _txn(
                    ref=ref(),
                    transaction_id=f"TRX-{day:%Y%m}-SAL",
                    amount="8450.00",
                    indicator="CRDT",
                    booked=day,
                    debtor="FIRMA PRZYKŁADOWA SP. Z O.O.",
                    debtor_iban=EMPLOYER_IBAN,
                    remittance=[f"Wynagrodzenie za {day:%m/%Y}"],
                    btc=RECEIVED,
                )
            )
        if day.day == 12:  # przelew własny na oszczędności — widoczny na obu kontach
            r = ref()
            main.append(
                _txn(
                    ref=r,
                    amount="1500.00",
                    indicator="DBIT",
                    booked=day,
                    creditor="Jan Testowy",
                    creditor_iban=SAVINGS_IBAN,
                    remittance=["Przelew własny oszczędności"],
                    btc=TRANSFER,
                )
            )
            savings.append(
                _txn(
                    ref=r + "S",
                    amount="1500.00",
                    indicator="CRDT",
                    booked=day,
                    debtor="Jan Testowy",
                    debtor_iban=MAIN_IBAN,
                    remittance=["Przelew własny oszczędności"],
                    btc=RECEIVED,
                )
            )
        if day.day == 15:  # rachunek za prąd
            main.append(
                _txn(
                    ref=ref(),
                    amount=_amount(rng, 180, 420),
                    indicator="DBIT",
                    booked=day,
                    creditor="TAURON SPRZEDAŻ SP. Z O.O.",
                    creditor_iban=TAURON_IBAN,
                    remittance=[f"Faktura P/{rng.randint(10000, 99999)}/{day:%m/%Y}"],
                    btc=TRANSFER,
                )
            )
        if day.day == 20:  # BLIK — bez MCC
            main.append(
                _txn(
                    ref=ref(),
                    amount=_amount(rng, 30, 150),
                    indicator="DBIT",
                    booked=day,
                    creditor="ALLEGRO.PL",
                    remittance=["BLIK zakup w internecie ALLEGRO.PL"],
                    btc=BLIK,
                )
            )
        day += timedelta(days=1)

    # Dwie identyczne transakcje tego samego dnia, bez identyfikatorów (dedup z licznikiem n)
    twin_day = today - timedelta(days=5)
    for _ in range(2):
        main.append(
            _txn(
                ref=None,
                amount="4.50",
                indicator="DBIT",
                booked=twin_day,
                creditor="AUTOMAT KAWA MPK",
                remittance=["Płatność kartą AUTOMAT KAWA MPK"],
                mcc="5814",
                btc=CARD,
            )
        )
    # Oczekujące (PDNG) — bez daty księgowania
    main.append(
        _txn(
            ref=None,
            amount="89.99",
            indicator="DBIT",
            booked=None,
            status="PDNG",
            tx_date=today,
            creditor="ZABKA Z1234",
            remittance=["Blokada środków ZABKA Z1234"],
            mcc="5411",
            btc=CARD,
        )
    )

    for txns in (main, savings):
        txns.sort(key=lambda t: t["booking_date"] or t["transaction_date"], reverse=True)

    def balances(txns: list[dict[str, Any]], opening: Decimal) -> list[dict[str, Any]]:
        total = opening
        for t in txns:
            if t["status"] == "BOOK":
                a = Decimal(t["transaction_amount"]["amount"])
                total += a if t["credit_debit_indicator"] == "CRDT" else -a
        return [
            {
                "name": name,
                "balance_amount": {"currency": "PLN", "amount": str(total)},
                "balance_type": btype,
                "reference_date": today.isoformat(),
                "last_change_date_time": None,
                "last_committed_transaction": None,
            }
            for btype, name in (("CLBD", "Saldo księgowe"), ("ITAV", "Saldo dostępne"))
        ]

    def info(iban: str, product: str) -> dict[str, Any]:
        return {
            "account_id": {"iban": iban},
            "all_account_ids": [],
            "name": "Jan Testowy",
            "product": product,
            "currency": "PLN",
            "cash_account_type": "CACC" if product != "Konto Oszczędnościowe" else "SVGS",
            "usage": "PRIV",
            "psu_status": "Account Holder",
            "details": product,
        }

    return {
        "accounts": [
            {
                "info": info(MAIN_IBAN, "Konto 360"),
                "transactions": main,
                "balances": balances(main, Decimal("5000.00")),
            },
            {
                "info": info(SAVINGS_IBAN, "Konto Oszczędnościowe"),
                "transactions": savings,
                "balances": balances(savings, Decimal("20000.00")),
            },
        ]
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--today", type=date.fromisoformat, default=date.today())
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    data = build(args.today)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    for acc in data["accounts"]:
        print(acc["info"]["product"], len(acc["transactions"]), "transakcji")


if __name__ == "__main__":
    main()
