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

from budget import (
    card,
    flex,
    forecast,
    invest,
    loan,
    loan_sim,
    piggy,
    savings,
    year,
    year_events,
)
from budget.money import ZERO, pl
from budget.recurring import schedule
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
    return parse_month(value or None, today)


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


# --- Cykliczne -------------------------------------------------------------------------------

MAX_SERIES = 30  # wierszy listy serii dla modelu


def _recurring(c: Ctx) -> SourceResult:
    mv = schedule.for_month(c.snap, c.month, c.today)
    cur = c.month == month_start(c.today)
    res = SourceResult(
        "recurring",
        link="/recurring" if cur else f"/recurring?month={c.month:%Y-%m}",
        link_label="Otwórz Cykliczne",
    )
    facts = res.facts
    facts.append(Fact("Miesiąc", month_label(c.month)))
    facts.append(Fact("Wydatki cykliczne zapłacone", pl(mv.out_paid, "PLN")))
    facts.append(Fact("Wydatki cykliczne do zapłaty", pl(mv.out_planned, "PLN")))
    facts.append(Fact("Wpływy cykliczne otrzymane", pl(mv.in_received, "PLN")))
    facts.append(Fact("Wpływy cykliczne oczekiwane", pl(mv.in_planned, "PLN")))
    late = mv.count(schedule.LATE)
    if late:
        facts.append(Fact("Spóźnione płatności", str(late)))
    rows = sorted(mv.rows, key=lambda d: d.sort_day)[:MAX_SERIES]
    for i, d in enumerate(rows, 1):
        paid = d.status in (schedule.PAID, schedule.EXTRA)
        kind = "wydatek" if d.series.direction == "out" else "wpływ"
        amount = d.paid_amount if paid else d.series.expected_amount
        when = f" · {_date(d.sort_day)}" if d.due or d.txns else ""
        value = f"{kind} {pl(amount, 'PLN')} · {schedule.STATUS_LABELS[d.status]}{when}"
        facts.append(Fact(d.series.name, value, llm_label=f"[Seria {i}]"))
    res.filters = ["Serie jak na ekranie Cykliczne: aktywne, z terminem i statusem w miesiącu"]
    return res


# --- Rok -------------------------------------------------------------------------------------


def _event_flow(e: year_events.Event) -> str:
    """Nowa seria ma kwotę bezwzględną — kierunek mówi słowem; reszta ma znak w kwocie."""
    if e.kind != "new_series":
        return ""
    return "wpływ " if e.direction == "in" else "wydatek "


def _event_span(e: year_events.Event) -> str:
    if e.kind == "one_off":
        return month_label(e.start)
    return f"od {month_label(e.start)}" + (f" do {month_label(e.end)}" if e.end else "")


def _year(c: Ctx) -> SourceResult:
    res = SourceResult("year", link="/year", link_label="Otwórz Rok")
    proj = year.build(c.snap, c.today, c.buffer)
    if proj is None:
        res.note = "Brak salda rachunku PLN w księdze — nie da się policzyć prognozy rocznej."
        return res
    facts = res.facts
    deficit = proj.first_deficit
    facts.append(Fact("Koniec horyzontu", _date(year.horizon_end(c.today))))
    facts.append(Fact("Saldo dziś", pl(proj.start_balance, "PLN")))
    facts.append(Fact("Saldo na koniec horyzontu", pl(proj.end, "PLN")))
    facts.append(Fact("Pierwszy deficyt", month_label(deficit) if deficit else "brak"))
    if proj.max_flex is not None:
        facts.append(Fact("Mogę wydać miesięcznie (elastyczne)", pl(proj.max_flex, "PLN")))
    facts.append(Fact("Elastyczne w prognozie (miesięcznie)", pl(proj.flex_month, "PLN")))
    if proj.scenario:
        facts.append(Fact("Saldo na koniec w scenariuszu", pl(proj.scenario.end, "PLN")))
    for m in proj.months:
        facts.append(Fact(f"Saldo na koniec: {month_label(m.month)}", pl(m.balance, "PLN")))
    for i, e in enumerate(year_events.active(c.conn), 1):
        facts.append(
            Fact(
                e.name,
                f"{year_events.KINDS[e.kind]} {_event_flow(e)}{pl(e.amount, 'PLN')} · "
                f"{_event_span(e)} · {year_events.MODES[e.mode].lower()}",
                f"[Seria {i}]",
            )
        )
    res.filters = [
        "Prognoza jak na ekranie Rok: serie, mediana elastycznych, roczne bez serii, zdarzenia",
        "Próg deficytu: " + (f"bufor {pl(proj.buffer, 'PLN')}" if proj.buffer > 0 else "zero"),
    ]
    return res


# --- Oszczędności i skarbonki ----------------------------------------------------------------


def _savings(c: Ctx) -> SourceResult:
    res = SourceResult("savings", link="/piggy", link_label="Otwórz Skarbonki")
    accounts = savings.all_accounts(c.conn)
    fc = forecast.for_today(c.snap, c.today, c.now, c.buffer)
    if fc is not None and fc.piggies_from is not None:
        rows = fc.piggies
    else:
        rows = piggy.statuses(c.snap, c.today, month_start(c.today))
    if not accounts and not rows:
        res.note = "Brak kont oszczędnościowych i skarbonek w panelu."
        return res
    facts = res.facts
    if accounts:
        ov = savings.overview(c.conn, c.today, 1)
        if ov is not None:
            facts.append(Fact("Saldo kont oszczędnościowych razem", pl(ov.total, "PLN")))
            cur = ov.current
            facts.append(Fact("Odłożone w tym miesiącu", pl(cur.saved, "PLN")))
            if cur.income:
                facts.append(
                    Fact("Stopa oszczędności w tym miesiącu", f"{cur.saved / cur.income:.0%}")
                )
        for i, a in enumerate(accounts, 1):
            est = savings.estimate(c.conn, a, c.today)
            value = f"{pl(est.total, 'PLN')} · odsetki netto {pl(est.interest, 'PLN')}"
            facts.append(Fact(a.name, value, llm_label=f"[Konto {i}]"))
    if rows:
        facts.append(
            Fact(
                "Do przelania na skarbonki w tym okresie", pl(piggy.total_to_transfer(rows), "PLN")
            )
        )
    for i, st in enumerate(rows, 1):
        parts = [f"saldo {pl(st.balance, 'PLN')}"]
        if st.target:
            parts.append(f"cel {pl(st.target, 'PLN')}")
        if st.due:
            parts.append(f"termin {_date(st.due)}")
        parts.append(f"do przelania {pl(st.to_transfer, 'PLN')}")
        facts.append(Fact(st.piggy.name, " · ".join(parts), llm_label=f"[Skarbonka {i}]"))
    res.filters = [
        "Salda i odsetki jak na ekranie Skarbonki (szacunek odsetek netto po podatku Belki)"
    ]
    return res


# --- Kredyt ----------------------------------------------------------------------------------


def _loan(c: Ctx) -> SourceResult:
    res = SourceResult("loan", link="/loan", link_label="Otwórz Kredyt")
    loans = loan.all_loans(c.conn)
    if not loans:
        res.note = "Brak kredytów w panelu."
        return res
    for i, lo in enumerate(loans, 1):
        s = loan.summary(lo, loan.schedule(lo), c.today)
        parts = [
            f"kapitał {pl(s.principal, 'PLN')}",
            f"najbliższa rata {pl(s.installment, 'PLN')}",
            f"oprocentowanie {lo.rate}% (stawka {lo.reference_rate}% + marża {lo.margin}%)",
            f"pozostało rat {s.count}",
        ]
        if s.payoff:
            parts.append(f"ostatnia rata {_date(s.payoff)}")
        parts.append(f"odsetki do końca {pl(s.interest_left, 'PLN')}")
        fc = loan_sim.forecast(c.conn, lo, c.today)
        if fc is not None:
            kind = "stawka banku" if fc.final else "prognoza"
            parts.append(
                f"od {_date(fc.reset)} rata {pl(fc.installment, 'PLN')} "
                f"({kind}, WIBOR 3M {fc.wibor}%)"
            )
        res.facts.append(Fact(lo.name, " · ".join(parts), llm_label=f"[Kredyt {i}]"))
    res.filters = ["Harmonogram jak na ekranie Kredyt: raty równe/malejące, odsetki 30/360"]
    return res


# --- Inwestycje ------------------------------------------------------------------------------

TOP_OPTIONS = 3


def _invest(c: Ctx) -> SourceResult:
    res = SourceResult("invest", link="/invest", link_label="Otwórz Inwestycje")
    fc = forecast.for_today(c.snap, c.today, c.now, c.buffer)
    proj = year.build(c.snap, c.today, c.buffer)
    adv = invest.advice(c.snap, fc, proj, c.today)
    if adv.rec.state == "no_data":
        res.note = "Brak prognozy rocznej w panelu — agent inwestycyjny nie ma z czego liczyć."
        return res
    facts = res.facts
    for b in adv.buckets:
        parts = [f"mam {pl(b.have, 'PLN')}"]
        if b.target is not None:
            parts += [f"cel {pl(b.target, 'PLN')}", f"brakuje {pl(b.gap, 'PLN')}"]
        facts.append(Fact(f"Koszyk: {b.label}", " · ".join(parts)))
    surplus = pl(adv.rec.surplus or ZERO, "PLN")
    facts.append(
        Fact("Nadwyżka miesięczna", f"brak ({surplus})" if adv.rec.state == "deficit" else surplus)
    )
    for p in adv.rec.parts:  # przy deficycie pusta
        name = invest.BUCKET_NAMES.get(p.bucket, "cele")
        if p.option is None:
            facts.append(Fact(f"Odłóż: {name}", f"{pl(p.amount, 'PLN')} → brak pasującej opcji"))
            continue
        kind = invest.OPTION_KINDS.get(p.option.key, "oferta")
        facts.append(  # nazwa banku, konta i kredytu zostaje w etykiecie, do modelu idzie rodzaj
            Fact(
                f"Odłóż: {name} → {p.option.label}",
                f"{pl(p.amount, 'PLN')} → {kind}",
                llm_label=f"Odłóż: {name} → [{kind}]",
            )
        )
    for i, o in enumerate(adv.options[:TOP_OPTIONS], 1):
        kind = invest.OPTION_KINDS.get(o.key, "oferta")
        access = "płynna" if o.liquid else "związana"
        value = f"{kind} · netto {pl(o.per_year, 'PLN')} rocznie · {access}"
        facts.append(Fact(o.label, value, llm_label=f"[Opcja {i}]"))
    res.filters = [
        f"Porównanie dla {pl(adv.amount, 'PLN')} na {invest.DEFAULT_YEARS} lat, netto po Belce",
        "Doradztwo: add-on niczego nie robi na kontach",
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
    Source(
        "recurring",
        "Cykliczne",
        "płatności i wpływy cykliczne miesiąca: co zapłacone, co jeszcze do zapłaty, terminy",
        _recurring,
        monthly=True,
    ),
    Source(
        "year",
        "Rok",
        "prognoza roczna: saldo na koniec roku, pierwszy deficyt, ile można wydawać miesięcznie, "
        "scenariusze",
        _year,
    ),
    Source(
        "savings",
        "Skarbonki",
        "konta oszczędnościowe (salda, odsetki, stopa oszczędności) i skarbonki (cel, postęp)",
        _savings,
    ),
    Source(
        "loan",
        "Kredyt",
        "kredyt hipoteczny: kapitał, rata, oprocentowanie, pozostałe raty, odsetki, zmiana stopy",
        _loan,
    ),
    Source(
        "invest",
        "Inwestycje",
        "agent inwestycyjny: koszyki (poduszka, cele, długi termin), ile odłożyć z nadwyżki, "
        "gdzie, najlepsze opcje (lokaty, konta, obligacje, nadpłata kredytu)",
        _invest,
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
