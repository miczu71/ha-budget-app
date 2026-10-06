"""Wydatki miesiąca w kategoriach — dane dla ekranu „Wydatki” (wzorzec `report.py`).

Zasady liczenia (`docs/PLAN_M4a.md`):
- miesiąc kalendarzowy po dacie transakcji (`tx_date`, bez niej data księgowania);
- tylko zaksięgowane, bez przelewów wewnętrznych (`transfer_group`), konta „w budżecie”;
- kwoty w PLN; transakcje w innej walucie są pomijane i liczone osobno (przeliczenie → M9);
- grupa podkategorii decyduje o sekcji: przychody, oszczędności, poza budżetem, reszta to
  wydatki; zwrot w kategorii wydatku zmniejsza ją (kwota netto);
- bilans = suma wszystkich uwzględnionych kwot.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from budget.categorize import taxonomy
from budget.categorize.taxonomy import Category

ZERO = Decimal(0)
BASE_CURRENCY = "PLN"


@dataclass
class Line:
    category: Category
    amount: Decimal = ZERO  # dodatnia = wydano (netto) / wpłynęło / odłożono
    count: int = 0
    prev: Decimal = ZERO  # poprzedni miesiąc

    @property
    def delta(self) -> Decimal:
        return self.amount - self.prev


@dataclass
class MainLine(Line):
    children: list[Line] = field(default_factory=list)
    share: float = 0.0  # udział w wydatkach miesiąca


@dataclass
class Coverage:
    """Pokrycie kategoriami (wydatki: kwoty ujemne bez przelewów wewnętrznych)."""

    txns: int = 0
    categorized: int = 0
    amount: Decimal = ZERO
    categorized_amount: Decimal = ZERO

    @property
    def pct_txns(self) -> float:
        return self.categorized / self.txns if self.txns else 0.0

    @property
    def pct_amount(self) -> float:
        return float(self.categorized_amount / self.amount) if self.amount else 0.0


@dataclass
class Month:
    month: date
    prev_month: date
    next_month: date | None  # None, gdy następny miesiąc jeszcze się nie zaczął
    income: Decimal = ZERO  # przychody (kategorie) + nieskategoryzowane wpływy
    expenses: Decimal = ZERO  # wydatki w kategoriach (netto) + nieskategoryzowane wydatki
    savings: Decimal = ZERO
    excluded: Decimal = ZERO
    balance: Decimal = ZERO
    expense_groups: list[MainLine] = field(default_factory=list)
    income_lines: list[Line] = field(default_factory=list)
    savings_lines: list[Line] = field(default_factory=list)
    excluded_lines: list[Line] = field(default_factory=list)
    uncategorized_out: Decimal = ZERO
    uncategorized_out_count: int = 0
    uncategorized_in: Decimal = ZERO
    uncategorized_in_count: int = 0
    coverage: Coverage = field(default_factory=Coverage)
    other_currency: int = 0
    # porównanie z poprzednim okresem: dla bieżącego (niepełnego) miesiąca ten sam zakres dni
    prev_income: Decimal = ZERO
    prev_expenses: Decimal = ZERO
    prev_balance: Decimal = ZERO
    prev_window: tuple[date, date] | None = None  # [od, do) poprzedniego okresu

    @property
    def prev_partial(self) -> bool:
        """Porównanie z częścią poprzedniego miesiąca (oglądany miesiąc jest jeszcze niepełny)."""
        return self.prev_window is not None and self.prev_window[1] < self.month


@dataclass(frozen=True)
class MonthTotals:
    month: date
    income: Decimal
    expenses: Decimal
    partial: bool  # bieżący miesiąc, jeszcze niepełny


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(y, m + 1, 1)


MONTHS = (
    "styczeń",
    "luty",
    "marzec",
    "kwiecień",
    "maj",
    "czerwiec",
    "lipiec",
    "sierpień",
    "wrzesień",
    "październik",
    "listopad",
    "grudzień",
)


MONTHS_GEN = (
    "stycznia",
    "lutego",
    "marca",
    "kwietnia",
    "maja",
    "czerwca",
    "lipca",
    "sierpnia",
    "września",
    "października",
    "listopada",
    "grudnia",
)


def month_label(d: date) -> str:
    return f"{MONTHS[d.month - 1]} {d.year}"


def parse_month(value: str | None, today: date) -> date:
    """`2026-09` → 1 września 2026; puste albo błędne → bieżący miesiąc (nie z przyszłości)."""
    try:
        y, m = (value or "").split("-")
        d = date(int(y), int(m), 1)
    except ValueError:
        return today.replace(day=1)
    return min(d, today.replace(day=1))


@dataclass
class _Acc:
    amount: Decimal = ZERO
    count: int = 0

    def add(self, amount: Decimal) -> None:
        self.amount += amount
        self.count += 1


@dataclass
class Sums:
    by_leaf: dict[int, _Acc] = field(default_factory=lambda: defaultdict(_Acc))  # ze znakiem
    unc_out: _Acc = field(default_factory=_Acc)  # wartości bezwzględne
    unc_in: _Acc = field(default_factory=_Acc)
    balance: Decimal = ZERO
    coverage: Coverage = field(default_factory=Coverage)
    other_currency: int = 0


DETAILS = (
    ", t.kind, t.merchant, t.counterparty_name, t.description, "
    "coalesce(t.tx_date, t.booking_date) AS day"
)


def section(leaf: Category | None, amount: Decimal) -> str:
    """Sekcja ekranu: grupa podkategorii (przychody / oszczędności / poza budżetem / reszta =
    wydatki); bez kategorii — znak kwoty."""
    if leaf is None:
        return "expenses" if amount < 0 else "income"
    if leaf.flex_group in ("income", "savings", "excluded"):
        return leaf.flex_group
    return "expenses"


def _rows(
    conn: sqlite3.Connection, start: date | None, end: date | None, details: bool = False
) -> list[sqlite3.Row]:
    """Transakcje liczone w budżecie; `details` dokłada pola opisowe (`DETAILS`, czat M12)."""
    where = [
        "t.status = 'BOOK'",
        "t.transfer_group IS NULL",
        "a.include_in_budget = 1",
    ]
    params: list[str] = []
    if start is not None:
        where.append("coalesce(t.tx_date, t.booking_date) >= ?")
        params.append(start.isoformat())
    if end is not None:
        where.append("coalesce(t.tx_date, t.booking_date) < ?")
        params.append(end.isoformat())
    return conn.execute(
        f"SELECT t.id, t.amount, t.currency, t.category_id{DETAILS if details else ''} FROM txn t "
        f"JOIN account a ON a.id = t.account_id WHERE {' AND '.join(where)}",
        params,
    ).fetchall()


def sums(
    conn: sqlite3.Connection,
    start: date | None,
    end: date | None,
    skip: Collection[int] = (),
) -> Sums:
    """Sumy okresu; transakcje z `skip` (np. serie liczone w puli, M5b E4) są pomijane."""
    s = Sums()
    for r in _rows(conn, start, end):
        if r["id"] in skip:
            continue
        if r["currency"] != BASE_CURRENCY:
            s.other_currency += 1
            continue
        amount = Decimal(r["amount"])
        s.balance += amount
        if amount < 0:
            s.coverage.txns += 1
            s.coverage.amount -= amount
            if r["category_id"] is not None:
                s.coverage.categorized += 1
                s.coverage.categorized_amount -= amount
        if r["category_id"] is None:
            (s.unc_out if amount < 0 else s.unc_in).add(abs(amount))
        else:
            s.by_leaf[int(r["category_id"])].add(amount)
    return s


def recent(conn: sqlite3.Connection, start: date, end: date, limit: int = 5) -> list[sqlite3.Row]:
    """Ostatnie zaksięgowane transakcje okresu [start, end) z tymi samymi filtrami co budżet."""
    return conn.execute(
        "SELECT t.id, t.amount, t.currency, t.merchant, t.counterparty_name, t.description, "
        "coalesce(t.tx_date, t.booking_date) AS day, c.name AS category_name "
        "FROM txn t JOIN account a ON a.id = t.account_id "
        "LEFT JOIN category c ON c.id = t.category_id "
        "WHERE t.status = 'BOOK' AND t.transfer_group IS NULL AND a.include_in_budget = 1 "
        "AND coalesce(t.tx_date, t.booking_date) >= ? AND coalesce(t.tx_date, t.booking_date) < ? "
        "ORDER BY day DESC, t.id DESC LIMIT ?",
        (start.isoformat(), end.isoformat(), limit),
    ).fetchall()


def totals(leaves: Mapping[int, Category], s: Sums) -> tuple[Decimal, Decimal]:
    """Wpływy i wydatki okresu z sum, wg reguł `build` (grupa podkategorii decyduje o sekcji)."""
    income, expenses = s.unc_in.amount, s.unc_out.amount
    for leaf in leaves.values():
        acc = s.by_leaf.get(leaf.id)
        if acc is None or leaf.flex_group in ("savings", "excluded"):
            continue
        if leaf.flex_group == "income":
            income += acc.amount
        else:
            expenses -= acc.amount  # wydatki są ujemne, zwrot zmniejsza kategorię
    return income, expenses


def monthly_totals(conn: sqlite3.Connection, today: date, n: int = 12) -> list[MonthTotals]:
    """Wpływy i wydatki ostatnich `n` miesięcy do bieżącego włącznie, od najstarszego."""
    leaves, current = taxonomy.leaves(conn), month_start(today)
    out = []
    for back in range(n - 1, -1, -1):
        month = add_months(current, -back)
        income, expenses = totals(leaves, sums(conn, month, add_months(month, 1)))
        out.append(MonthTotals(month, income, expenses, month == current))
    return out


def coverage(
    conn: sqlite3.Connection, start: date | None = None, end: date | None = None
) -> Coverage:
    """Pokrycie wydatków kategoriami w okresie (bez granic = cała księga)."""
    return sums(conn, start, end).coverage


def build(conn: sqlite3.Connection, month: date, today: date) -> Month:
    start = month_start(month)
    prev_start = add_months(start, -1)
    nxt = add_months(start, 1)
    cur, prev = sums(conn, start, nxt), sums(conn, prev_start, start)
    out = Month(
        month=start,
        prev_month=prev_start,
        next_month=nxt if nxt <= today else None,
        balance=cur.balance,
        coverage=cur.coverage,
        other_currency=cur.other_currency,
    )
    # rzetelne porównanie: bieżący miesiąc z tym samym zakresem dni poprzedniego, nie z całym
    prev_end = start
    if start == month_start(today):
        prev_end = min(prev_start + timedelta(days=today.day), start)
    prev_window = prev if prev_end == start else sums(conn, prev_start, prev_end)
    out.prev_window = (prev_start, prev_end)
    out.prev_income, out.prev_expenses = totals(taxonomy.leaves(conn), prev_window)
    out.prev_balance = prev_window.balance
    out.uncategorized_out, out.uncategorized_out_count = cur.unc_out.amount, cur.unc_out.count
    out.uncategorized_in, out.uncategorized_in_count = cur.unc_in.amount, cur.unc_in.count

    for main in taxonomy.tree(conn):
        group = MainLine(main.category)
        for leaf in main.children:
            now, before = cur.by_leaf.get(leaf.id, _Acc()), prev.by_leaf.get(leaf.id, _Acc())
            sign = 1 if leaf.flex_group == "income" else -1  # przychód: +, reszta: wydano
            line = Line(leaf, sign * now.amount, now.count, sign * before.amount)
            if leaf.flex_group == "income":
                out.income_lines.append(line)
                out.income += line.amount
            elif leaf.flex_group == "savings":
                out.savings_lines.append(line)
                out.savings += line.amount
            elif leaf.flex_group == "excluded":
                out.excluded_lines.append(line)
                out.excluded += line.amount
            else:
                group.children.append(line)
                group.amount += line.amount
                group.count += line.count
                group.prev += line.prev
        if group.children and (group.count or group.prev):
            group.children = [c for c in group.children if c.count or c.prev]
            group.children.sort(key=lambda c: c.amount, reverse=True)
            out.expense_groups.append(group)
    out.expense_groups.sort(key=lambda g: g.amount, reverse=True)
    out.expenses = sum((g.amount for g in out.expense_groups), ZERO) + out.uncategorized_out
    out.income += out.uncategorized_in
    for g in out.expense_groups:
        g.share = float(g.amount / out.expenses) if out.expenses > 0 else 0.0
    out.income_lines = [line for line in out.income_lines if line.count or line.prev]
    out.savings_lines = [line for line in out.savings_lines if line.count or line.prev]
    out.excluded_lines = [line for line in out.excluded_lines if line.count or line.prev]
    return out
