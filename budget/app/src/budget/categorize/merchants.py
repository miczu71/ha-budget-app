"""Sprzedawca transakcji i wbudowany słownik sieci (`merchants_pl.toml`).

Źródło nazwy sprzedawcy zależy od typu transakcji:
- karta (i zwrot na kartę) — opis (nazwa, adres punktu, kraj, data);
- BLIK — pole kontrahenta (zwykle domena sklepu), bez niego opis;
- gotówka — operator bankomatu z pola kontrahenta;
- przelewy, zlecenia, polecenia zapłaty, kredyt, opłaty — odbiorca/zleceniodawca. Tytułu
  przelewu słownik nie czyta: „Netflix” w tytule przelewu od osoby to nie subskrypcja.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from budget.kinds import Kind
from budget.normalize import fold, merchant_ident

_DESCRIPTION_KINDS = frozenset({Kind.CARD.value, Kind.CARD_REFUND.value})
_COUNTERPARTY_FIRST = frozenset({Kind.BLIK.value, Kind.BLIK_REFUND.value, Kind.CASH.value})
_WORD_RE = re.compile(r"[A-Z0-9]+")
_DOMAIN_RE = re.compile(r"^(?:https?://)?(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)(?:[/\s(]|$)")
DISPLAY_MAX = 60


class DictionaryError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    slug: str  # podkategoria
    pattern: tuple[str, ...]
    name: str | None  # marka (None = słowo ogólne, nazwa zostaje z opisu)
    order: int


class Dictionary:
    """Wzorce jednowyrazowe w słowniku (szybkie wyszukiwanie), wielowyrazowe na liście."""

    def __init__(self, version: int, entries: tuple[Entry, ...]) -> None:
        self.version = version
        self.entries = entries
        self._single: dict[str, list[Entry]] = {}
        self._multi: list[Entry] = []
        for e in entries:
            if len(e.pattern) == 1:
                self._single.setdefault(e.pattern[0], []).append(e)
            else:
                self._multi.append(e)

    def match(self, text: str | None) -> Entry | None:
        """Najdłuższy pasujący wzorzec: więcej słów, przy remisie marka przed słowem ogólnym
        („CARREFOUR SUPERMARKET” → Carrefour), potem więcej znaków, potem kolejność w pliku."""
        tokens = words(text)
        if not tokens:
            return None
        found = [e for t in set(tokens) for e in self._single.get(t, ())]
        joined = f" {' '.join(tokens)} "
        found += [e for e in self._multi if f" {' '.join(e.pattern)} " in joined]
        if not found:
            return None
        return min(
            found,
            key=lambda e: (-len(e.pattern), e.name is None, -len("".join(e.pattern)), e.order),
        )


def words(text: str | None) -> list[str]:
    """Słowa po normalizacji: wielkie litery bez polskich znaków, tylko litery i cyfry."""
    return _WORD_RE.findall(fold(text))


def _pattern(raw: str, where: str) -> tuple[str, ...]:
    pattern = tuple(words(raw))
    if not pattern or " ".join(pattern) != raw:
        raise DictionaryError(f"{where}: wzorzec „{raw}” nie jest w postaci znormalizowanej")
    return pattern


def parse(data: dict[str, Any]) -> Dictionary:
    version = data.get("version")
    if not isinstance(version, int):
        raise DictionaryError("brak pola version")
    entries: list[Entry] = []
    seen: dict[tuple[str, ...], str] = {}

    def add(slug: str, raw: str, name: str | None, where: str) -> None:
        pattern = _pattern(raw, where)
        if pattern in seen:
            raise DictionaryError(
                f"{where}: wzorzec „{raw}” powtórzony (pierwszy: {seen[pattern]})"
            )
        seen[pattern] = where
        entries.append(Entry(slug, pattern, name, len(entries)))

    for slug, brands in data.get("brands", {}).items():
        for name, patterns in brands.items():
            for raw in patterns:
                add(slug, raw, name, f"brands.{slug}.{name}")
    for slug, patterns in data.get("keywords", {}).items():
        for raw in patterns:
            add(slug, raw, None, f"keywords.{slug}")
    return Dictionary(version, tuple(entries))


@cache
def builtin() -> Dictionary:
    """Słownik dostarczany z add-onem."""
    text = resources.files("budget.categorize").joinpath("merchants_pl.toml").read_text("utf-8")
    return parse(tomllib.loads(text))


def source_text(kind: str, description: str | None, counterparty_name: str | None) -> str:
    """Pole, w którym siedzi sprzedawca/odbiorca (docstring modułu)."""
    if kind in _DESCRIPTION_KINDS:
        return description or ""
    if kind in _COUNTERPARTY_FIRST:
        return counterparty_name or description or ""
    return counterparty_name or ""


def _tidy(text: str) -> str:
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    if text.isupper():
        text = text.title()
    return text[:DISPLAY_MAX]


def base_merchant(kind: str, description: str | None, counterparty_name: str | None) -> str:
    """Nazwa sprzedawcy/odbiorcy do wyświetlania i reguł (przed słownikiem i regułami)."""
    text = source_text(kind, description, counterparty_name)
    if not text and kind not in _DESCRIPTION_KINDS:
        return _tidy(description or "")  # np. rata kredytu bez kontrahenta
    if m := _DOMAIN_RE.match(text.strip().lower()):
        return m.group(1)
    if kind in _DESCRIPTION_KINDS or kind in _COUNTERPARTY_FIRST:
        ident = merchant_ident(text)
        return _tidy(ident) if ident else _tidy(text)
    return _tidy(text)
