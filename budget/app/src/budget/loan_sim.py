"""Kalkulator scenariuszy kredytu (M9 E3a, decyzja 28): nadpłata, zmiana WIBOR i marży,
porównanie z oszczędnościami.

Porównanie na koniec horyzontu: obie opcje wydają co miesiąc tyle samo gotówki (rata z harmonogramu
bazowego + nadpłata miesięczna), a kwota nadpłaty dziś trafia do kredytu albo na konto. Opcja
„nadpłata” odkłada na konto to, co kredyt zabiera mniej (niższa rata, spłata przed terminem);
opcja „oszczędności” spłaca kredyt wg bazowego harmonogramu. Wynik = (saldo konta − kapitał
kredytu) pierwszej opcji minus drugiej; konto liczone odsetkami netto (Belka) jak w `savings`.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from budget import loan, money, savings, wibor
from budget.loan import Installment, Loan, Scenario
from budget.spending import add_months

ZERO = money.ZERO
STEPS = (
    Decimal(1),
    Decimal("0.5"),
    Decimal("0.25"),
)  # dozwolone kroki WIBOR w tabeli wariantów, p.p.


@dataclass(frozen=True)
class Outcome:
    rows: list[Installment]

    @property
    def installment(self) -> Decimal:
        return self.rows[0].payment if self.rows else ZERO

    @property
    def payoff(self) -> date | None:
        return self.rows[-1].day if self.rows else None

    @property
    def interest(self) -> Decimal:
        return sum((r.interest for r in self.rows), ZERO)


@dataclass(frozen=True)
class Result:
    base: Outcome  # tylko zmiany stóp, bez nadpłaty
    scen: Outcome
    horizon_end: date
    loan_rate: Decimal  # stopa kredytu dziś w scenariuszu, % rocznie
    savings_gross: Decimal  # efektywna stopa konta dla kwoty nadpłaty, % rocznie
    wealth_overpay: Decimal
    wealth_save: Decimal

    @property
    def savings_net(self) -> Decimal:
        return self.savings_gross * (1 - savings.BELKA)

    @property
    def interest_saved(self) -> Decimal:
        return self.base.interest - self.scen.interest

    @property
    def gain(self) -> Decimal:
        """Plus: nadpłata wychodzi lepiej niż oszczędności; minus: odwrotnie."""
        return self.wealth_overpay - self.wealth_save


def account_for(
    real: savings.Account | None, rate: Decimal | None = None, always_promo: bool = False
) -> savings.Account:
    """Konto do porównania: wpisana stopa (bez promocji), konto z promocją do jej końca albo
    — z `always_promo` — przez cały horyzont (do limitu kwoty), albo konto bez stóp (0%)."""
    if rate is not None or real is None:
        return savings.Account(0, "", "", ZERO, date.min, base_rate=rate)
    if always_promo and real.promo_rate is not None:
        limit = real.promo_limit or savings.PROMO_FUNDS_MAX
        return replace(real, promo_until=date.max, promo_limit=limit)
    return real


def _horizon(today: date, months: int) -> date:
    """Ten sam dzień miesiąca `months` miesięcy później (przycięty do długości miesiąca)."""
    first = add_months(today, months)
    return first.replace(day=min(today.day, calendar.monthrange(first.year, first.month)[1]))


def _start(lo: Loan, today: date) -> tuple[Decimal, date, Installment | None]:
    """Kapitał dziś, dzień ostatniej raty do dziś i rata bazowa (ziarno) najbliższa po dziś."""
    rows = loan.schedule(lo)
    done = [r for r in rows if r.day <= today]
    k = len(done)
    return (
        done[-1].balance if done else lo.principal,
        done[-1].day if done else lo.principal_date,
        rows[k] if k < len(rows) else None,
    )


@dataclass(frozen=True)
class Forecast:
    """Rata po zmianie oprocentowania przy WIBOR `wibor` z notowania `quote_day`."""

    reset: date  # dzień zmiany oprocentowania (przyszły albo już miniony, gdy kredyt nieaktualny)
    wibor: Decimal
    quote_day: date
    final: bool  # dzień ustalenia stawki już minął — to nie prognoza, tylko stawka banku
    rate: Decimal  # oprocentowanie po zmianie, % rocznie
    installment: Decimal  # pierwsza rata po zmianie
    current: Decimal  # rata przed zmianą

    @property
    def delta(self) -> Decimal:
        return self.installment - self.current

    @property
    def fixing(self) -> date:
        return wibor.fixing_day(self.reset)


def _after_reset(
    lo: Loan, today: date, quote: tuple[date, Decimal], reset: date, final: bool
) -> Forecast | None:
    """Raty kredytu przy nowej stawce od `reset`; None, gdy kredyt jest już spłacony."""
    balance, prev, seed = _start(lo, today)
    scen = Scenario(wibor_delta=quote[1] - lo.reference_rate, wibor_from=reset)
    rows = loan.run(lo, balance, prev, today, scen, seed)
    before = loan.run(lo, balance, prev, today, None, seed)
    new = next((r for r in rows if r.day >= reset), None)
    if not rows or new is None:
        return None
    return Forecast(
        reset, quote[1], quote[0], final, lo.rate + quote[1] - lo.reference_rate,
        new.payment, before[0].payment,
    )  # fmt: skip


def pending(conn: sqlite3.Connection, lo: Loan, today: date) -> Forecast | None:
    """Zmiana oprocentowania, która już była, a kredyt w panelu jej nie uwzględnia: stawka z dnia
    ustalenia inna niż WIBOR w kredycie i kredyt wpisany przed zmianą (`principal_date`)."""
    if lo.rate_reset_date is None:
        return None
    reset = loan.resets(lo.rate_reset_date, today)[0]
    quote = wibor.at(conn, wibor.fixing_day(reset))
    if quote is None or quote[1] == lo.reference_rate or lo.principal_date >= reset:
        return None
    return _after_reset(lo, today, quote, reset, True)


def forecast(conn: sqlite3.Connection, lo: Loan, today: date) -> Forecast | None:
    """Rata od najbliższej zmiany oprocentowania: z ostatniego notowania, a po dniu ustalenia
    stawki — z notowania z tego dnia. None: brak daty zmiany lub notowań albo kredyt czeka na
    korektę."""
    if lo.rate_reset_date is None or pending(conn, lo, today):
        return None
    reset = loan.resets(lo.rate_reset_date, today)[1]
    fixed = wibor.at(conn, wibor.fixing_day(reset)) if today >= wibor.fixing_day(reset) else None
    quote = fixed or wibor.at(conn, today)
    return _after_reset(lo, today, quote, reset, fixed is not None) if quote else None


def _grow(
    acc: savings.Account, start: Decimal, today: date, dates: list[date], deposits: list[Decimal]
) -> Decimal:
    bal, prev = start, today
    for day, deposit in zip(dates, deposits, strict=True):
        gross = savings.daily(acc, bal, prev) * (day - prev).days
        bal += savings.net(gross) + deposit
        prev = day
    return bal


def _balance(rows: list[Installment], dates: list[date], start: Decimal) -> Decimal:
    done = [r for r in rows if r.day <= dates[-1]] if dates else []
    return done[-1].balance if done else start


def simulate(
    lo: Loan,
    scen: Scenario,
    today: date,
    acc: savings.Account,
    months: int | None = None,
) -> Result | None:
    """Wynik scenariusza na horyzoncie `months` (None = do końca kredytu); None, gdy spłacony."""
    balance, prev, seed = _start(lo, today)
    when = max(today, prev)
    no_overpay = replace(scen, lump=ZERO, monthly=ZERO)
    base = loan.run(lo, balance, prev, when, no_overpay, seed)
    if not base:
        return None
    mine = loan.run(lo, balance, prev, when, scen, seed)
    end = base[-1].day if months is None else _horizon(today, months)
    dates = [r.day for r in base if r.day <= end]
    by_day = {r.day: r for r in mine}
    zero = Installment(today, ZERO, ZERO, ZERO)
    spent = [r.payment + scen.monthly for r in base if r.day <= end]
    paid = [by_day.get(d, zero).payment + by_day.get(d, zero).extra for d in dates]
    over = [s - p for s, p in zip(spent, paid, strict=True)]
    wealth_over = _grow(acc, ZERO, when, dates, over) - _balance(mine, dates, balance - scen.lump)
    wealth_save = _grow(acc, scen.lump, when, dates, [scen.monthly] * len(dates)) - _balance(
        base, dates, balance
    )
    probe = scen.lump or Decimal(1000)
    gross = savings.daily(acc, probe, when) * 365 * 100 / probe
    return Result(
        Outcome(base),
        Outcome(mine),
        end,
        scen.rate(lo, when, when),
        gross,
        wealth_over.quantize(money.CENT),
        wealth_save.quantize(money.CENT),
    )


def overpay_gain(lo: Loan, lump: Decimal, today: date, months: int | None = None) -> Decimal | None:
    """Zysk z jednorazowej nadpłaty (krótszy okres) względem trzymania gotówki bez odsetek, na
    koniec horyzontu: zaoszczędzone odsetki i raty (bez oprocentowania uwolnionej gotówki).
    Na całym okresie kredytu = zaoszczędzone odsetki; None, gdy kredyt spłacony."""
    res = simulate(lo, Scenario(lump=lump), today, account_for(None), months)
    if res is None:
        return None
    done = [r for r in res.base.rows if r.day <= res.horizon_end]
    base_balance = done[-1].balance if done else _start(lo, today)[0]
    return (res.wealth_overpay + base_balance - lump).quantize(money.CENT)


def variants(
    lo: Loan, scen: Scenario, today: date, step: Decimal = STEPS[0]
) -> list[tuple[Decimal, Outcome, Outcome, Outcome]]:
    """Tabela: zmiana WIBOR (−2…+2 kroki po `step`) × (bez nadpłaty, krótszy okres, niższa rata),
    ta sama nadpłata."""
    balance, prev, seed = _start(lo, today)
    when = max(today, prev)
    out = []
    for delta in (step * k for k in range(-2, 3)):
        sc = replace(scen, wibor_delta=delta)

        def run(s: Scenario) -> Outcome:
            return Outcome(loan.run(lo, balance, prev, when, s, seed))

        out.append(
            (
                delta,
                run(replace(sc, lump=ZERO, monthly=ZERO)),
                run(replace(sc, variant="shorten")),
                run(replace(sc, variant="lower")),
            )
        )
    return out
