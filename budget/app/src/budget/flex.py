"""Budżet Flex (M5a): „ile mogę jeszcze wydać w tym miesiącu” — dane dla ekranu „Budżet”.

Zasady (`docs/PLAN_M5a.md`, decyzja 13 w `docs/ROADMAP.md`):
- pula = kwota ustawiona ręcznie; obowiązuje od miesiąca do następnej zmiany (`flex_budget`),
  więc zmiana „od tego miesiąca” nie przepisuje wcześniejszych;
- „wydane” = netto podkategorii z grupy `flexible` + wydatki bez kategorii (ostrożnie — po
  skategoryzowaniu jako stałe albo nieregularne kwota wraca do puli);
- stałe i nieregularne tylko informacyjnie; przychody, oszczędności i „poza budżetem” pomijane;
- reszta jak w `spending`: miesiąc kalendarzowy, bez przelewów wewnętrznych, tylko PLN;
- tempo liniowe: do końca dzisiejszego dnia „powinno” być wydane budżet × dzień / dni miesiąca;
- mediany i podpowiedź kwoty z `HISTORY_MONTHS` pełnych miesięcy przed miesiącem ekranu, tylko
  od miesiąca pierwszej transakcji w księdze (miesiące bez wydatków w kategorii liczą się jako 0).
"""

from __future__ import annotations

import calendar
import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, Decimal

from budget import money
from budget.categorize import taxonomy
from budget.categorize.taxonomy import Category
from budget.spending import BASE_CURRENCY, ZERO, Sums, add_months, month_start, sums
from budget.storage.db import now_iso

HISTORY_MONTHS = 6
BUDGET_MAX = Decimal("10000000")


class FlexError(ValueError):
    """Komunikat dla użytkownika panelu."""


@dataclass
class FlexLine:
    category: Category
    parent: str  # nazwa kategorii głównej
    amount: Decimal  # wydane netto w miesiącu
    count: int
    median: Decimal  # mediana miesięczna z historii


@dataclass
class HistoryMonth:
    month: date
    spent: Decimal  # jak `FlexMonth.spent`
    uncategorized: Decimal  # w tym bez kategorii


@dataclass
class FlexMonth:
    month: date
    prev_month: date
    next_month: date | None  # None, gdy następny miesiąc jeszcze się nie zaczął
    budget: Decimal | None  # None — kwota nieustawiona
    budget_from: date | None  # od którego miesiąca obowiązuje kwota
    spent: Decimal  # elastyczne netto + bez kategorii
    uncategorized: Decimal
    uncategorized_count: int
    fixed: Decimal  # informacyjnie
    non_monthly: Decimal  # informacyjnie
    days_in_month: int
    day: int | None  # dzisiejszy dzień miesiąca; None dla miesięcy minionych
    lines: list[FlexLine] = field(default_factory=list)
    history: list[HistoryMonth] = field(default_factory=list)
    other_currency: int = 0

    @property
    def is_current(self) -> bool:
        return self.day is not None

    @property
    def remaining(self) -> Decimal | None:
        return None if self.budget is None else self.budget - self.spent

    @property
    def days_left(self) -> int:
        """Dni do końca miesiąca łącznie z dzisiejszym (0 dla miesięcy minionych)."""
        return self.days_in_month - self.day + 1 if self.day is not None else 0

    @property
    def per_day(self) -> Decimal | None:
        """Ile można wydawać dziennie do końca miesiąca (0, gdy pula wyczerpana)."""
        if self.remaining is None or not self.days_left:
            return None
        return (max(self.remaining, ZERO) / self.days_left).quantize(money.CENT)

    @property
    def elapsed(self) -> float:
        """Część miesiąca, która minęła (z dzisiejszym dniem) — kreska tempa na pasku."""
        return self.day / self.days_in_month if self.day is not None else 1.0

    @property
    def expected(self) -> Decimal | None:
        """Ile przy równym tempie powinno być wydane do końca dzisiejszego dnia."""
        if self.budget is None or self.day is None:
            return None
        return (self.budget * self.day / self.days_in_month).quantize(money.CENT)

    @property
    def over_pace(self) -> bool:
        return self.expected is not None and self.spent > self.expected

    @property
    def used(self) -> float:
        """Wydane / budżet (do szerokości paska; może przekroczyć 1)."""
        return float(self.spent / self.budget) if self.budget else 0.0

    @property
    def suggested(self) -> Decimal | None:
        """Podpowiedź kwoty: mediana „wydane” z historii, w górę do pełnych 10 zł."""
        if not self.history:
            return None
        median = Decimal(statistics.median(h.spent for h in self.history))
        return max((median / 10).to_integral_value(ROUND_CEILING) * 10, Decimal(10))


# --- kwota budżetu ----------------------------------------------------------------------------


def budget_for(conn: sqlite3.Connection, month: date) -> tuple[Decimal, date] | None:
    """Kwota obowiązująca w miesiącu i miesiąc, od którego obowiązuje."""
    row = conn.execute(
        "SELECT month_from, amount FROM flex_budget WHERE month_from <= ? "
        "ORDER BY month_from DESC LIMIT 1",
        (month_start(month).isoformat(),),
    ).fetchone()
    if row is None:
        return None
    return Decimal(row["amount"]), date.fromisoformat(row["month_from"])


def parse_amount(value: str) -> Decimal:
    try:
        amount = money.parse(value)
    except money.AmountError:
        amount = None
    if amount is None or amount <= 0 or amount >= BUDGET_MAX:
        raise FlexError("Podaj kwotę budżetu większą od zera, np. 2500 albo 2 500,00.")
    return amount


def set_budget(conn: sqlite3.Connection, month: date, amount: Decimal) -> None:
    """Kwota od miesiąca `month` (do następnej zmiany)."""
    conn.execute(
        "INSERT INTO flex_budget (month_from, amount, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (month_from) DO UPDATE SET amount = excluded.amount, "
        "updated_at = excluded.updated_at",
        (month_start(month).isoformat(), money.fmt(amount), now_iso()),
    )


# --- wyliczenie -------------------------------------------------------------------------------


def _first_month(conn: sqlite3.Connection) -> date | None:
    row = conn.execute(
        "SELECT min(coalesce(t.tx_date, t.booking_date)) FROM txn t "
        "JOIN account a ON a.id = t.account_id "
        "WHERE t.status = 'BOOK' AND a.include_in_budget = 1 AND t.currency = ?",
        (BASE_CURRENCY,),
    ).fetchone()
    return month_start(date.fromisoformat(row[0][:10])) if row and row[0] else None


def _history(conn: sqlite3.Connection, start: date) -> list[tuple[date, Sums]]:
    """Pełne miesiące przed `start` (najwyżej `HISTORY_MONTHS`), od pierwszej transakcji."""
    first = _first_month(conn)
    if first is None:
        return []
    out = []
    for n in range(HISTORY_MONTHS, 0, -1):
        m = add_months(start, -n)
        if m >= first:
            out.append((m, sums(conn, m, add_months(m, 1))))
    return out


def _spent(s: Sums, flexible: list[Category]) -> Decimal:
    net = sum((s.by_leaf[c.id].amount for c in flexible if c.id in s.by_leaf), ZERO)
    return s.unc_out.amount - net  # kwoty wydatków są ujemne


def _group(s: Sums, leaves: list[Category], group: str) -> Decimal:
    return -sum(
        (s.by_leaf[c.id].amount for c in leaves if c.flex_group == group and c.id in s.by_leaf),
        ZERO,
    )


def build(conn: sqlite3.Connection, month: date, today: date) -> FlexMonth:
    start = month_start(month)
    nxt = add_months(start, 1)
    cur = sums(conn, start, nxt)
    history = _history(conn, start)
    parents = {m.category.id: m.category.name for m in taxonomy.tree(conn)}
    leaves = list(taxonomy.leaves(conn).values())
    flexible = [c for c in leaves if c.flex_group == "flexible"]
    current = start == month_start(today)
    budget = budget_for(conn, start)

    out = FlexMonth(
        month=start,
        prev_month=add_months(start, -1),
        next_month=nxt if nxt <= today else None,
        budget=budget[0] if budget else None,
        budget_from=budget[1] if budget else None,
        spent=_spent(cur, flexible),
        uncategorized=cur.unc_out.amount,
        uncategorized_count=cur.unc_out.count,
        fixed=_group(cur, leaves, "fixed"),
        non_monthly=_group(cur, leaves, "non_monthly"),
        days_in_month=calendar.monthrange(start.year, start.month)[1],
        day=today.day if current else None,
        history=[HistoryMonth(m, _spent(s, flexible), s.unc_out.amount) for m, s in history],
        other_currency=cur.other_currency,
    )
    for c in flexible:
        acc = cur.by_leaf.get(c.id)
        past = [-s.by_leaf[c.id].amount if c.id in s.by_leaf else ZERO for _, s in history]
        median = Decimal(statistics.median(past)) if past else ZERO
        if acc is None and not median:
            continue
        amount, count = (-acc.amount, acc.count) if acc else (ZERO, 0)
        out.lines.append(FlexLine(c, parents.get(c.parent_id or 0, ""), amount, count, median))
    out.lines.sort(key=lambda line: (line.amount, line.median), reverse=True)
    return out
