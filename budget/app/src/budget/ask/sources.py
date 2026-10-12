"""Rejestr źródeł danych czatu (M12 E3b, decyzja 24).

Każda funkcja panelu z własnymi danymi to źródło: nazwa, jedno zdanie dla modelu i funkcja, która
woła ten sam kod co jej ekran i zwraca fakty (etykieta → wartość). Do LLM idą kwoty, ale nie nazwy
własne (osoby, konta, skarbonki, kredyty): te zastępują etykiety `[K1]`… podmieniane lokalnie
(`SourceResult.labels`, `engine.restore`). Źródło „transactions” to język zapytań z `query.py`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from budget import forecast
from budget.money import ZERO, pl
from budget.snapshot import Snapshot
from budget.spending import month_start, parse_month

TRANSACTIONS = "transactions"


class SourceError(ValueError):
    """Źródło nieznane albo nie do policzenia — komunikat dla użytkownika."""


@dataclass(frozen=True)
class Fact:
    label: str  # etykieta w tabeli (może zawierać nazwę własną)
    value: str  # gotowy zapis: kwota, data, liczba albo zdanie
    llm_label: str = ""  # etykieta dla modelu, gdy `label` zawiera nazwę własną


@dataclass
class SourceResult:
    source: str
    facts: list[Fact] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)  # „jak policzono”
    link: str = "/"  # ekran źródła (bez przedrostka Ingress)
    link_label: str = "Otwórz ekran"
    note: str = ""  # brak danych — odpowiedź bez pytania modelu

    @property
    def labels(self) -> dict[str, str]:
        """Etykieta dla LLM → prawdziwa nazwa (tylko tam, gdzie się różnią)."""
        return {f.llm_label: f.label for f in self.facts if f.llm_label and f.llm_label != f.label}

    def for_llm(self) -> dict[str, Any]:
        """Fakty po redakcji — jedyne dane źródła, które idą do LLM."""
        return {
            "source": self.source,
            "facts": [{"label": f.llm_label or f.label, "value": f.value} for f in self.facts],
            "filters": self.filters,
        }


@dataclass(frozen=True)
class Ctx:
    conn: sqlite3.Connection
    snap: Snapshot
    today: date
    now: datetime
    month: date  # miesiąc z planu (bieżący, gdy źródło nie ma miesiąca)
    buffer: Decimal = ZERO  # bufor prognozy z opcji add-onu


Builder = Callable[[Ctx], SourceResult]


@dataclass(frozen=True)
class Source:
    name: str
    label: str  # nazwa ekranu w panelu
    description: str  # jedno zdanie dla modelu
    build: Builder
    monthly: bool = False  # ekran ma przełącznik miesięcy


def month_of(value: str, today: date) -> date:
    """Miesiąc z planu: pusty albo błędny = bieżący."""
    return parse_month(value or None, today) if value else month_start(today)


def _date(d: date) -> str:
    return f"{d:%d.%m.%Y}"


# --- Do wypłaty ------------------------------------------------------------------------------


def _payday(c: Ctx) -> SourceResult:
    res = SourceResult("payday", link="/", link_label="Otwórz Podsumowanie")
    fc = forecast.for_today(c.snap, c.today, c.now, c.buffer)
    if fc is None:
        res.note = "Brak salda rachunku PLN w księdze — nie da się policzyć prognozy do wypłaty."
        return res
    facts = res.facts
    if fc.payday:
        facts.append(Fact("Najbliższa wypłata", _date(fc.payday)))
    facts.append(Fact("Dni do końca okresu", str(fc.days_left)))
    facts.append(Fact("Wolne środki dziś", pl(fc.free_now, "PLN")))
    if fc.balances:
        facts.append(Fact("Saldo rachunku", pl(fc.balances.account, "PLN")))
        facts.append(Fact("Zadłużenie karty", pl(fc.balances.card_debt, "PLN")))
    facts.append(
        Fact(
            "Zadłużenie karty odjęte od wolnych środków", "tak" if fc.card_debt_included else "nie"
        )
    )
    if fc.low_day:
        facts.append(Fact("Najniższe saldo do wypłaty", pl(fc.low, "PLN")))
        facts.append(Fact("Dzień najniższego salda", _date(fc.low_day)))
    facts.append(Fact("Saldo w dniu wypłaty", pl(fc.at_payday, "PLN")))
    facts.append(Fact("Bufor", pl(fc.buffer, "PLN")))
    facts.append(
        Fact(
            "Starczy do wypłaty",
            "nie, brakuje " + pl(fc.shortfall, "PLN") if fc.below_buffer else "tak",
        )
    )
    if fc.safe_per_day is not None:
        facts.append(Fact("Bezpieczny limit dzienny (elastyczne)", pl(fc.safe_per_day, "PLN")))
    facts.append(Fact("Wydane elastyczne od wypłaty", pl(fc.spent_since, "PLN")))
    res.filters = [
        "Prognoza jak na ekranie Podsumowanie: saldo PLN, serie cykliczne, pula elastyczna",
        "Wolne środki = saldo rachunku" + (" − zadłużenie karty" if fc.card_debt_included else ""),
    ]
    return res


REGISTRY: tuple[Source, ...] = (
    Source(
        "payday",
        "Do wypłaty",
        "czy starczy do następnej wypłaty: wolne środki, saldo, dług karty, najniższe saldo, "
        "limit dzienny",
        _payday,
    ),
)
NAMES = tuple(s.name for s in REGISTRY)
_BY_NAME = {s.name: s for s in REGISTRY}


def prompt_lines() -> list[str]:
    return [
        f"  - {s.name}: {s.description}" + (" (ma miesiąc)" if s.monthly else "") for s in REGISTRY
    ]


def run(name: str, c: Ctx, month: str = "") -> SourceResult:
    """`c.month` zostaje bieżący dla źródeł bez miesiąca; `month` — RRRR-MM z planu."""
    source = _BY_NAME.get(name)
    if source is None:
        raise SourceError(f"nieznane źródło {name!r}")
    return source.build(replace(c, month=month_of(month, c.today) if source.monthly else c.month))
