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

from budget import card, flex, forecast
from budget.money import ZERO, pl
from budget.snapshot import Snapshot
from budget.spending import month_label, month_start, parse_month

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


# --- Karta -----------------------------------------------------------------------------------


def _card(c: Ctx) -> SourceResult:
    res = SourceResult("card", link="/card", link_label="Otwórz Kartę")
    cm = card.month_status(c.conn, c.month)
    if cm is None:
        res.note = "Brak konta karty kredytowej w księdze."
        return res
    facts = res.facts
    facts.append(Fact("Miesiąc", month_label(cm.month)))
    if cm.shared:
        h = cm.holders[0]
        facts.append(Fact("Płatności kartą w miesiącu", _count(h.count, h.threshold)))
    else:
        facts.append(Fact("Płatności kartą w miesiącu", str(cm.count)))
        for i, h in enumerate(cm.holders, 1):
            facts.append(Fact(h.name, _count(h.count, h.threshold), llm_label=f"[Osoba {i}]"))
        if cm.unassigned:
            facts.append(Fact("Płatności bez przypisanej osoby", str(cm.unassigned)))
    if cm.month == month_start(c.today):
        facts.append(Fact("Dni do końca miesiąca", str(card.days_to_end(c.today))))
        due = card.due_status(c.conn, c.today)
        if due is not None:
            facts.append(Fact("Do spłaty w terminie", pl(due.left, "PLN")))
            facts.append(Fact("Termin spłaty", _date(due.due)))
            facts.append(Fact("Zadłużenie karty", pl(due.debt, "PLN")))
            if due.limit:
                facts.append(Fact("Limit karty", pl(due.limit, "PLN")))
    res.filters = [
        "Licznik jak na ekranie Karta: płatności kartą w miesiącu (mniejsza z liczb po dacie "
        "księgowania i po dacie zakupu), karta bezpłatna przy " + str(card.THRESHOLD),
        "Do spłaty = zadłużenie − nowe zakupy po zamknięciu cyklu (jak kafelek Karta)",
    ]
    return res


def _count(count: int, threshold: int) -> str:
    left = max(threshold - count, 0)
    return f"{count} z {threshold}" + (f" (brakuje {left})" if left else "")


# --- Budżet ----------------------------------------------------------------------------------


def _budget(c: Ctx) -> SourceResult:
    f = flex.build(c.snap, c.month, c.today)
    res = SourceResult("budget", link=f"/budget?month={c.month:%Y-%m}", link_label="Otwórz Budżet")
    facts = res.facts
    facts.append(Fact("Miesiąc", month_label(f.month)))
    if f.budget is None:
        facts.append(Fact("Budżet elastyczny", "nie ustawiono"))
    else:
        how = "ręczny" if f.budget_source == "manual" else "z dochodu"
        facts.append(Fact("Budżet elastyczny", pl(f.budget, "PLN")))
        facts.append(Fact("Źródło kwoty budżetu", how))
    facts.append(Fact("Wydane elastyczne", pl(f.spent, "PLN")))
    if f.remaining is not None:
        facts.append(Fact("Zostało w budżecie elastycznym", pl(f.remaining, "PLN")))
    if f.is_current:
        facts.append(Fact("Dni do końca miesiąca", str(f.days_left)))
        if f.per_day is not None:
            facts.append(Fact("Można wydawać dziennie", pl(f.per_day, "PLN")))
        if f.expected is not None:
            facts.append(Fact("Przy równym tempie powinno być wydane", pl(f.expected, "PLN")))
            facts.append(Fact("Wydatki szybsze od tempa", "tak" if f.over_pace else "nie"))
    facts.append(Fact("Koszty stałe (informacyjnie)", pl(f.fixed, "PLN")))
    facts.append(Fact("Wydatki nieregularne (informacyjnie)", pl(f.non_monthly, "PLN")))
    if f.uncategorized_count:
        facts.append(
            Fact(
                "Bez kategorii (w wydanych)",
                f"{pl(f.uncategorized, 'PLN')} ({f.uncategorized_count} tr.)",
            )
        )
    res.filters = ["Budżet jak na ekranie Budżet: pula elastyczna z dochodu albo wpisana ręcznie"]
    return res


REGISTRY: tuple[Source, ...] = (
    Source(
        "payday",
        "Do wypłaty",
        "czy starczy do następnej wypłaty: wolne środki, saldo, dług karty, najniższe saldo, "
        "limit dzienny",
        _payday,
    ),
    Source(
        "card",
        "Karta",
        "karta kredytowa: płatności w miesiącu (próg 5, per osoba), kwota do spłaty, termin, limit",
        _card,
        monthly=True,
    ),
    Source(
        "budget",
        "Budżet",
        "budżet elastyczny miesiąca: pula, wydane, ile zostało, ile można wydawać dziennie, tempo",
        _budget,
        monthly=True,
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
