"""Podsumowanie roku (M25 E2): sumy, porównanie r/r, zmiany kategorii, rekordy i stopa oszczędności.

Zasady (`docs/PLAN_M25_E2.md`):
- zakres roku: [1 stycznia, 1 stycznia następnego); rok bieżący kończy się jutrem (dziś włącznie);
- porównanie r/r: ten sam zakres dni rok wcześniej; rok zamknięty porównywany jest z całym
  poprzednim rokiem (ten sam zakres dni dałby brakujące 31 grudnia w roku przestępnym);
- sumy, sekcje i netto zwrotów jak w `spending`; stopa oszczędności z `savings.monthly_rates`
  (wpłaty na konta oszczędnościowe, bez przelewów między nimi);
- rekordy liczone z jednego przebiegu transakcji: kwoty dodatnie, wydatek = część w sekcji
  „expenses”, transakcja z podziałem (M29) liczy się raz.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from budget import flex, savings, spending
from budget.categorize import taxonomy
from budget.categorize.taxonomy import Category

ZERO = Decimal(0)
CHANGE_MIN = Decimal(200)  # próg zmiany kategorii głównej (zł, także spadek)
TOP = 5  # ile zmian (wzrostów / spadków) pokazać
MERCHANTS = 10  # ile sprzedawców w zestawieniu roku
NOT_EXPENSE = ("income", "savings", "excluded")


@dataclass(frozen=True)
class Change:
    category: Category  # kategoria główna
    amount: Decimal  # wydatki okresu, dodatnie (netto)
    prev: Decimal  # wydatki tego samego zakresu rok wcześniej

    @property
    def delta(self) -> Decimal:
        return self.amount - self.prev


@dataclass(frozen=True)
class Pick:
    day: date
    label: str  # sprzedawca / opis transakcji
    amount: Decimal  # dodatnia


@dataclass(frozen=True)
class Streak:
    start: date
    end: date  # włącznie
    days: int


@dataclass(frozen=True)
class Records:
    biggest_expense: Pick | None
    priciest_month: tuple[date, Decimal] | None  # miesiąc z najwyższymi wydatkami (bez bieżącego)
    priciest_day: tuple[date, Decimal] | None  # dzień z najwyższymi wydatkami netto
    flex_free: Streak | None  # najdłuższa seria dni bez wydatku elastycznego
    biggest_income: Pick | None


@dataclass(frozen=True)
class PrevPeriod:
    start: date
    end: date  # wyłącznie
    income: Decimal
    expenses: Decimal


@dataclass(frozen=True)
class Recap:
    year: int
    start: date
    end: date  # wyłącznie
    partial: bool  # rok bieżący, jeszcze trwa
    income: Decimal
    expenses: Decimal
    prev: PrevPeriod | None  # None, gdy księga nie sięga poprzedniego zakresu
    months: list[spending.MonthTotals]  # 12 miesięcy roku
    savings_rate: Decimal | None  # Σodłożone / Σwpływy miesięcy roku
    best_month: savings.MonthRate | None
    worst_month: savings.MonthRate | None
    rises: list[Change]
    falls: list[Change]
    merchants: list[spending.Merchant]
    records: Records


def years(conn: sqlite3.Connection, today: date) -> list[int]:
    """Lata od roku pierwszej transakcji do bieżącego, malejąco; pusta księga → []."""
    first = flex.first_day(conn)
    if first is None:
        return []
    return list(range(today.year, first.year - 1, -1))


def _window(year: int, today: date) -> tuple[date, date]:
    return date(year, 1, 1), min(date(year + 1, 1, 1), today + timedelta(days=1))


def _prev_window(
    conn: sqlite3.Connection, year: int, start: date, end: date
) -> tuple[date, date] | None:
    prev_start = date(year - 1, 1, 1)
    first = flex.first_day(conn)
    if first is None or first > prev_start:
        return None
    if end == date(year + 1, 1, 1):  # rok zamknięty: cały poprzedni rok
        return prev_start, date(year, 1, 1)
    return prev_start, prev_start + (end - start)


def _net(s: spending.Sums, leaves: list[Category]) -> Decimal:
    return sum((s.by_leaf[c.id].amount for c in leaves if c.id in s.by_leaf), ZERO)


def _changes(
    conn: sqlite3.Connection, cur: spending.Sums, prev: spending.Sums
) -> tuple[list[Change], list[Change]]:
    """Kategorie główne z wydatkami, których zmiana r/r przekracza `CHANGE_MIN` (top `TOP`)."""
    rises: list[Change] = []
    falls: list[Change] = []
    for main in taxonomy.tree(conn):
        leaves = [c for c in main.children if c.flex_group not in NOT_EXPENSE]
        if not leaves:
            continue
        change = Change(main.category, -_net(cur, leaves), -_net(prev, leaves))
        if change.delta >= CHANGE_MIN:
            rises.append(change)
        elif change.delta <= -CHANGE_MIN:
            falls.append(change)
    rises.sort(key=lambda c: c.delta, reverse=True)
    falls.sort(key=lambda c: c.delta)
    return rises[:TOP], falls[:TOP]


def _months(
    conn: sqlite3.Connection, year: int, end: date, today: date
) -> list[spending.MonthTotals]:
    """12 miesięcy roku; bieżący liczony do `end`, miesiące po dziś są zerowe."""
    leaves, current = taxonomy.leaves(conn), spending.month_start(today)
    out = []
    for m in range(1, 13):
        month = date(year, m, 1)
        if month > current:
            out.append(spending.MonthTotals(month, ZERO, ZERO, False))
            continue
        nxt = min(spending.add_months(month, 1), end)
        income, expenses = spending.totals(leaves, spending.sums(conn, month, nxt))
        out.append(spending.MonthTotals(month, income, expenses, month == current))
    return out


def _pick(amounts: dict[int, Decimal], labels: dict[int, tuple[date, str]]) -> Pick | None:
    if not amounts:
        return None
    txn = min(amounts, key=lambda t: (-amounts[t], t))
    day, label = labels[txn]
    return Pick(day, label, amounts[txn])


def _flex_free(flex_days: set[date], start: date, end: date) -> Streak | None:
    """Najdłuższa seria dni [start, end) bez wydatku elastycznego (remis: wcześniejsza)."""
    best: Streak | None = None
    run: date | None = None
    day = start
    while day < end:
        if day in flex_days:
            run = None
        else:
            run = day if run is None else run
            days = (day - run).days + 1
            if best is None or days > best.days:
                best = Streak(run, day, days)
        day += timedelta(days=1)
    return best


def _records(
    conn: sqlite3.Connection, start: date, end: date, months: list[spending.MonthTotals]
) -> Records:
    leaves: Mapping[int, Category] = taxonomy.leaves(conn)
    gross: dict[int, Decimal] = defaultdict(Decimal)  # wydatki transakcji (części razem)
    received: dict[int, Decimal] = defaultdict(Decimal)  # wpływy transakcji
    labels: dict[int, tuple[date, str]] = {}
    net_day: dict[date, Decimal] = defaultdict(Decimal)  # wydatki netto dnia
    flex_days: set[date] = set()
    for r in spending._rows(conn, start, end, details=True):
        if r["currency"] != spending.BASE_CURRENCY:
            continue
        amount = Decimal(r["amount"])
        cid = r["category_id"]
        leaf = leaves.get(int(cid)) if cid is not None else None
        day = date.fromisoformat(r["day"][:10])
        txn = int(r["id"])
        labels.setdefault(txn, (day, spending._merchant_group(r)[1]))
        section = spending.section(leaf, amount)
        if section == "income" and amount > 0:
            received[txn] += amount
        elif section == "expenses":
            net_day[day] += -amount
            if amount < 0:
                gross[txn] += -amount
                if leaf is None or leaf.flex_group == "flexible":
                    flex_days.add(day)
    closed = [m for m in months if not m.partial and m.expenses > 0]
    priciest_month = min(closed, key=lambda m: (-m.expenses, m.month), default=None)
    priciest_day = min(
        ((d, v) for d, v in net_day.items() if v > 0), key=lambda kv: (-kv[1], kv[0]), default=None
    )
    return Records(
        biggest_expense=_pick(gross, labels),
        priciest_month=(priciest_month.month, priciest_month.expenses) if priciest_month else None,
        priciest_day=priciest_day,
        flex_free=_flex_free(flex_days, max(start, flex.first_day(conn) or start), end),
        biggest_income=_pick(received, labels),
    )


def build(conn: sqlite3.Connection, year: int, today: date) -> Recap:
    """Podsumowanie roku `year` na dzień `today` (rok bieżący: do dziś włącznie)."""
    start, end = _window(year, today)
    leaves = taxonomy.leaves(conn)
    cur = spending.sums(conn, start, end)
    income, expenses = spending.totals(leaves, cur)

    prev: PrevPeriod | None = None
    rises: list[Change] = []
    falls: list[Change] = []
    window = _prev_window(conn, year, start, end)
    if window is not None:
        prev_sums = spending.sums(conn, *window)
        p_income, p_expenses = spending.totals(leaves, prev_sums)
        prev = PrevPeriod(window[0], window[1], p_income, p_expenses)
        rises, falls = _changes(conn, cur, prev_sums)

    # stopa: `n` miesięcy od stycznia roku do bieżącego włącznie (zakres obejmuje cały rok)
    rates = [
        r
        for r in savings.monthly_rates(conn, today, (today.year - year) * 12 + today.month)
        if r.month.year == year
    ]
    total_income = sum((r.income for r in rates), ZERO)
    savings_rate = sum((r.saved for r in rates), ZERO) / total_income if total_income > 0 else None
    scored = [r for r in rates if r.rate is not None and r.month != spending.month_start(today)]
    months = _months(conn, year, end, today)
    return Recap(
        year=year,
        start=start,
        end=end,
        partial=year == today.year,
        income=income,
        expenses=expenses,
        prev=prev,
        months=months,
        savings_rate=savings_rate,
        best_month=max(scored, key=lambda r: r.rate or ZERO, default=None),
        worst_month=min(scored, key=lambda r: r.rate or ZERO, default=None),
        rises=rises,
        falls=falls,
        merchants=spending.merchants(conn, None, start, end)[:MERCHANTS],
        records=_records(conn, start, end, months),
    )
