"""Anonimizacja eksportu „Historia transakcji” z Millenetu do fixture'a testowego (M7).

Zachowuje to, co ważne dla parsera: kodowanie (UTF-8 z BOM), CRLF, cytowanie wszystkich pól,
nagłówek, formaty dat i kwot, układ kolumn, puste pola, typy transakcji („Rodzaj transakcji”).
Zamienia: numery rachunków/kart (spójnie — ten sam numer zawsze na ten sam fałszywy, więc
przelewy własne dalej się parują), strony przelewów w „Odbiorca/Zleceniodawca” (osoby i firmy,
z adresami), tytuły przelewów,
ciągi cyfr w opisach; kwoty dostają jitter (znak zachowany), saldo jest przeliczane spójnie,
daty przesunięte o stały offset. Nazwy sklepów/firm w opisach płatności kartą zostają (potrzebne
do testów reguł kategoryzacji).

Wybiera próbkę: wszystkie typy transakcji, puste kwoty, a dla kart także zduplikowane bloki
(eksport karty kredytowej zawiera te same transakcje pod dwoma numerami kart).

Użycie: python tools/anonymize_millenet.py WEJŚCIE.csv WYJŚCIE.csv [--per-type 6] [--seed 7]
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ACCOUNT = "Numer rachunku/karty"
TX_DATE = "Data transakcji"
SETTLE_DATE = "Data rozliczenia"
KIND = "Rodzaj transakcji"
OTHER_ACC = "Na konto/Z konta"
PARTY = "Odbiorca/Zleceniodawca"
DESC = "Opis"
DEBIT = "Obciążenia"
CREDIT = "Uznania"
BALANCE = "Saldo"

COMPANY_MARKERS = re.compile(
    r"\b(SP\.? ?Z ?O\.? ?O|S\.? ?A\.?$|S\.A\.|SPÓŁKA|SPOLKA|SP\. ?J|SP\. ?K|BANK|"
    r"URZĄD|URZAD|ZUS|GMINA|FUNDACJA|STOWARZYSZENIE|SKLEP|ALLEGRO|TAURON|PGE|ORANGE|"
    r"PLAY|PLUS|T-MOBILE|NETFLIX|SPOTIFY|GOOGLE|APPLE|PAYU|PRZELEWY24|TPAY)\b",
    re.IGNORECASE,
)
# Typy, w których „Opis” to tytuł przelewu wpisany przez człowieka (może zawierać dane osobowe)
FREE_TEXT_KINDS = re.compile(r"PRZELEW|ZLECENIE|POLECENIE|^$")
DATE_SHIFT = timedelta(days=-14)


class Anonymizer:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.numbers: dict[str, str] = {}
        self.people: dict[str, str] = {}

    def number(self, value: str) -> str:
        """Fałszywy numer o tym samym kształcie (spacje, litery, gwiazdki zostają)."""
        if not value.strip():
            return value
        key = re.sub(r"\D", "", value)
        if key not in self.numbers:
            fake = "".join(str(self.rng.randint(0, 9)) for _ in key)
            self.numbers[key] = fake
        digits = iter(self.numbers[key])
        return re.sub(r"\d", lambda _: next(digits), value)

    def party(self, value: str, free_text: bool) -> str:
        """Sklep przy płatności kartą/BLIK zostaje; strona przelewu (osoba albo firma —
        np. pracodawca z adresem) zawsze dostaje pseudonim, firma z zachowanym znacznikiem."""
        if not value.strip():
            return value
        if not free_text:
            return self.digits(value)
        key = value.strip().upper()
        if key not in self.people:
            n = len(self.people) + 1
            company = COMPANY_MARKERS.search(value)
            self.people[key] = (
                f"FIRMA TESTOWA {n:03d} SP. Z O.O." if company else (f"OSOBA TESTOWA {n:03d}")
            )
        return self.people[key]

    def digits(self, value: str) -> str:
        """Ciągi ≥ 4 cyfr (numery kart, telefonów, faktur, referencji) → losowe cyfry."""
        return re.sub(
            r"\d{4,}", lambda m: "".join(str(self.rng.randint(0, 9)) for _ in m.group()), value
        )

    def amount(self, value: str) -> str:
        if not value:
            return value
        factor = Decimal(str(round(self.rng.uniform(0.7, 1.3), 3)))
        out = (Decimal(value) * factor).quantize(Decimal("0.01"))
        if out == 0:
            out = Decimal("0.01").copy_sign(Decimal(value))
        return str(out)


def _shift(value: str) -> str:
    return (date.fromisoformat(value) + DATE_SHIFT).isoformat() if value else value


def _sample(rows: list[dict[str, str]], per_type: int, rng: random.Random) -> list[dict[str, str]]:
    """Po `per_type` wierszy każdego (konto-typ, Rodzaj transakcji) + przypadki brzegowe."""
    groups: dict[tuple[bool, str], list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        is_card = len(re.sub(r"\D", "", r[ACCOUNT])) != 26
        groups[(is_card, r[KIND])].append(i)
    chosen: set[int] = set()
    for idx in groups.values():
        chosen.update(rng.sample(idx, min(per_type, len(idx))))
    chosen.update(i for i, r in enumerate(rows) if not r[DEBIT] and not r[CREDIT])
    # Duplikaty kart: dla wybranych wierszy kart dobierz identyczne wiersze spod drugiego numeru
    sig = lambda r: (r[TX_DATE], r[SETTLE_DATE], r[DEBIT], r[CREDIT], r[DESC])  # noqa: E731
    card_rows = [i for i in chosen if len(re.sub(r"\D", "", rows[i][ACCOUNT])) != 26]
    wanted = {sig(rows[i]) for i in card_rows}
    chosen.update(
        i
        for i, r in enumerate(rows)
        if len(re.sub(r"\D", "", r[ACCOUNT])) != 26 and sig(r) in wanted
    )
    return [rows[i] for i in sorted(chosen)]


def _recompute_balances(rows: list[dict[str, str]], rng: random.Random) -> None:
    """Saldo spójne z (zanonimizowanymi) kwotami; wiersze są od najnowszych, per rachunek."""
    by_account: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_account[r[ACCOUNT]].append(r)
    for acc_rows in by_account.values():
        if not any(r[BALANCE] for r in acc_rows):
            continue  # karty nie mają salda w eksporcie
        balance = Decimal(rng.randint(3000, 15000)).quantize(Decimal("0.01"))
        for r in acc_rows:  # od najnowszego: saldo po transakcji, potem cofamy
            r[BALANCE] = str(balance)
            balance -= Decimal(r[CREDIT] or r[DEBIT] or "0")


def anonymize(src: bytes, per_type: int, seed: int) -> bytes:
    bom = src.startswith(b"\xef\xbb\xbf")
    text = src.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text[:2000] else "\n"
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fields = list(reader.fieldnames or [])
    rows = list(reader)

    anon = Anonymizer(seed)
    out_rows = []
    for r in _sample(rows, per_type, anon.rng):
        r = dict(r)
        r[ACCOUNT] = anon.number(r[ACCOUNT])
        r[OTHER_ACC] = anon.number(r[OTHER_ACC])
        r[TX_DATE] = _shift(r[TX_DATE])
        r[SETTLE_DATE] = _shift(r[SETTLE_DATE])
        free_text = bool(FREE_TEXT_KINDS.search(r[KIND]))
        r[PARTY] = anon.party(r[PARTY], free_text)
        if free_text:
            r[DESC] = f"TYTUŁ PRZELEWU {anon.rng.randint(100, 999)}" if r[DESC].strip() else ""
        else:
            r[DESC] = anon.digits(r[DESC])
        r[DEBIT] = anon.amount(r[DEBIT])
        r[CREDIT] = anon.amount(r[CREDIT])
        out_rows.append(r)
    _recompute_balances(out_rows, anon.rng)

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields, quoting=csv.QUOTE_ALL, lineterminator=newline)
    writer.writeheader()
    writer.writerows(out_rows)
    return (b"\xef\xbb\xbf" if bom else b"") + buf.getvalue().encode("utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("src", type=Path)
    p.add_argument("dst", type=Path)
    p.add_argument("--per-type", type=int, default=6)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    args.dst.write_bytes(anonymize(args.src.read_bytes(), args.per_type, args.seed))


if __name__ == "__main__":
    main()
