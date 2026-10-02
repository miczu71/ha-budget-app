"""Normalizacja tekstów transakcji do porównań (odcisk, klucz sprzedawcy).

Opisy z Millennium są cięte na stałą szerokość — w API ze wstawioną spacją w środku słowa
(„Wrocl aw”), w CSV twardą spacją co 45 znaków. Dlatego odcisk opisu pomija wszystkie
znaki niealfanumeryczne, a klucz sprzedawcy opiera się na pierwszym znaczącym słowie.
"""

from __future__ import annotations

import re
import unicodedata

NBSP = "\xa0"

# Opis płatności kartą na rachunku: „SPRZEDAWCA ULICA MIASTO KRAJ RRRR-MM-DD”
CARD_DESC_RE = re.compile(r"\s([A-Z]{3})\s+(\d{4}-\d{2}-\d{2})\s*$")
# Prefiks komunikatu BLIK w API („/OPT/X///// …”, zwrot: „/OPF/…”)
_BLIK_PREFIX_RE = re.compile(r"^/OP[A-Z]/\S*\s*")
_TOKEN_RE = re.compile(r"[A-Z][A-Z0-9&'.-]*")
_ADDRESS = frozenset({"UL", "UL.", "AL", "AL.", "OS", "ULICA", "ALEJA"})
# Słowa, które nie identyfikują sprzedawcy
_STOP = frozenset(
    {
        "UL",
        "AL",
        "OS",
        "PL",
        "SP",
        "Z",
        "O",
        "OO",
        "SA",
        "THE",
        "WWW",
        "PAYU",
        "PAYPRO",
        "AUTOPAY",
        "PRZELEWY24",
    }
)


def fold(text: str | None) -> str:
    """Wielkie litery bez polskich znaków i twardych spacji, pojedyncze spacje."""
    if not text:
        return ""
    text = text.replace("ł", "l").replace("Ł", "L").replace(NBSP, " ")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text.upper()).strip()


def desc_key(text: str | None) -> str:
    """Opis do odcisku: tylko litery i cyfry — odporne na miejsca cięcia linii."""
    return re.sub(r"[^A-Z0-9]", "", fold(text))


def card_desc_date(text: str | None) -> str | None:
    """Data transakcji z opisu płatności kartą na rachunku (`… POL 2026-09-30`)."""
    m = CARD_DESC_RE.search(fold(text))
    return m.group(2) if m else None


def merchant_tokens(text: str | None) -> list[str]:
    """Znaczące słowa początku opisu (bez prefiksów BLIK, numerów i słów-wypełniaczy)."""
    folded = _BLIK_PREFIX_RE.sub("", fold(text))
    folded = folded.split(",")[0]  # opis z eksportu karty: „SPRZEDAWCA , MIASTO , KRAJ”
    out = []
    for i, token in enumerate(_TOKEN_RE.findall(folded)):
        token = token.strip(".-'")
        # Za nazwą zaczyna się numer sklepu/kasy albo adres („ZABKA Z1234 UL. …”);
        # cyfry dopuszczalne tylko w pierwszym słowie („P4”)
        if i and (token in _ADDRESS or any(ch.isdigit() for ch in token)):
            break
        if len(token) < 2 or token in _STOP:
            continue
        out.append(token)
    return out


def merchant_key(text: str | None, words: int = 2) -> str:
    """Klucz sprzedawcy: pierwsze znaczące słowa (`AMZN*N42BJ…` → `AMZN`)."""
    return " ".join(merchant_tokens(text)[:words])


def same_merchant(a: str | None, b: str | None) -> bool:
    """Ten sam sprzedawca, jeśli zgadza się pierwsze znaczące słowo (min. 3 znaki)."""
    ka, kb = merchant_key(a, 1), merchant_key(b, 1)
    return len(ka) >= 3 and ka == kb
