"""Co z transakcji wychodzi do LLM (ROADMAP, decyzja 12) — reszta zostaje w add-onie.

- płatność kartą / BLIK: nazwa sprzedawcy i opis (to nazwy firm i punktów);
- pozostałe (przelewy, zlecenia, polecenia zapłaty, …): wyłącznie tytuł — bez nazwy odbiorcy
  i bez jej słów w tytule; odbiorca bywa osobą prywatną;
- zawsze: kwota tylko jako przedział, bez dat, numerów kont i kart, e-maili, telefonów,
  kodów pocztowych (ciągi cyfr wycinane w całości).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from budget.countries import card_origin
from budget.kinds import CARD_KINDS, Kind
from budget.normalize import fold

KIND_LABELS = {
    Kind.CARD.value: "płatność kartą",
    Kind.CARD_REFUND.value: "zwrot na kartę",
    Kind.BLIK.value: "płatność BLIK",
    Kind.BLIK_REFUND.value: "zwrot BLIK",
    Kind.PHONE_TRANSFER.value: "przelew na telefon",
    Kind.TRANSFER_IN.value: "przelew przychodzący",
    Kind.TRANSFER_OUT.value: "przelew wychodzący",
    Kind.STANDING_ORDER.value: "zlecenie stałe",
    Kind.DIRECT_DEBIT.value: "polecenie zapłaty",
    Kind.CASH.value: "wypłata gotówki",
    Kind.LOAN.value: "rata kredytu",
    Kind.FEE.value: "opłata bankowa",
}
MAX_TEXTS = 3
TEXT_MAX = 80
_BOUNDS = (Decimal(20), Decimal(100), Decimal(500), Decimal(2000))

_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){11,30}\b")
_EMAIL_RE = re.compile(r"\S+@\S+")
_DIGITS_RE = re.compile(r"\+?\d[\d\s./-]{3,}\d")  # numery, daty, telefony, kody pocztowe
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Txn:
    """Pola transakcji potrzebne do opisu grupy (nic poza nimi nie trafia do `describe`)."""

    kind: str
    amount: Decimal
    description: str
    counterparty_name: str
    orig_currency: str | None = None


def scrub(text: str | None) -> str:
    """Tekst bez IBAN-ów, e-maili i ciągów cyfr (≥ 5 znaków), skrócony."""
    text = _IBAN_RE.sub(" ", text or "")
    text = _EMAIL_RE.sub(" ", text)
    text = _DIGITS_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip(" ,.;:-/")[:TEXT_MAX]


def without_name(text: str, *names: str) -> str:
    """Tytuł bez słów nazwy odbiorcy — także odmienionych („dla Qwertowskiego”); porównanie
    bez wielkości liter i polskich znaków, po rdzeniu (słowo nazwy bez 2 ostatnich liter)."""
    stems = {
        (w[: max(3, len(w) - 2)], len(w)) for n in names for w in fold(n).split() if len(w) >= 2
    }

    def banned(word: str) -> bool:
        w = fold(word).strip(",.;:")
        return any(w.startswith(stem) and len(w) <= size + 4 for stem, size in stems)

    return " ".join(w for w in text.split() if not banned(w)).strip(" ,.;:-/")


def amount_range(amount: Decimal) -> str:
    size = abs(amount)
    low = Decimal(0)
    for high in _BOUNDS:
        if size < high:
            return f"{low}–{high} zł"
        low = high
    return f"powyżej {low} zł"


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(abs(v) for v in values)
    return ordered[len(ordered) // 2]


def describe(merchant: str, direction: str, txns: Sequence[Txn]) -> dict[str, Any]:
    """Opis grupy (sprzedawca + kierunek) dla promptu — jedyne dane wysyłane do LLM."""
    kind = Counter(t.kind for t in txns).most_common(1)[0][0]
    card = kind in CARD_KINDS
    out: dict[str, Any] = {
        "rodzaj": KIND_LABELS.get(kind, "inna operacja"),
        "kierunek": "wydatek" if direction == "out" else "wpływ",
        "kwota": amount_range(_median([t.amount for t in txns])),
        "liczba": len(txns),
    }
    texts: Counter[str] = Counter()
    for t in txns:
        if card:
            text = scrub(t.description)
        else:
            text = without_name(scrub(t.description), t.counterparty_name, merchant)
        if text:
            texts[text] += 1
    if card:
        out["sprzedawca"] = scrub(merchant)
        countries = {
            o.label for t in txns if (o := card_origin(t.kind, t.description, t.orig_currency))
        }
        if countries:
            out["kraj"] = ", ".join(sorted(countries))
    out["opisy"] = [text for text, _ in texts.most_common(MAX_TEXTS)]
    return out
