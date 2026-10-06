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
  od miesiąca pierwszej transakcji w księdze (miesiące bez wydatków w kategorii liczą się jako 0);
- bez ręcznej kwoty pula jest automatyczna (etap 3, decyzja 14, `docs/PLAN_M5a_income.md`):
  wpływy z podkategorii `POOL_INCOME` (wynagrodzenie, świadczenia) z poprzedniego miesiąca
  − stałe; „Inne wpływy” (jednorazowe) nie zasilają puli (decyzja 22); nadwyżka nietypowo
  wysokiego wpływu ze źródła (premia) zostaje poza pulą;
- stałe = suma median podkategorii z grupy `fixed` (etap 4, decyzja 15,
  `docs/PLAN_M5a_fixed.md`) — składniki sumują się do kwoty w puli;
- serie cykliczne (M5b E4, decyzja 4, `docs/PLAN_M5b_E4.md`): aktywna seria wydatkowa wchodzi
  do stałych kwotą oczekiwaną w przeliczeniu na miesiąc, a jej transakcje wypadają z „wydane”,
  median i „poza pulą” (bez podwójnego liczenia). Wyjątek: seria, której ostatnia transakcja
  ma kategorię z grupy oszczędności, przychodów albo „poza budżetem” — nie zmienia puli.
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
from budget.recurring import series as S
from budget.recurring.series import Series
from budget.snapshot import Snapshot
from budget.spending import BASE_CURRENCY, ZERO, Sums, add_months, month_start, sums
from budget.storage.db import now_iso

HISTORY_MONTHS = 6
BUDGET_MAX = Decimal("10000000")
BONUS_WINDOW = 12  # miesięcy historii źródła wpływu do wykrycia premii
BONUS_MIN_MONTHS = 3  # krótsza historia źródła = wpływ liczony w całości
BONUS_RATIO = Decimal("1.5")  # premia: wpływ > 1,5 × 3. kwartyl miesięcznych wpływów źródła
BONUS_TYPICAL_MONTHS = 3  # do puli idzie mediana z ostatnich miesięcy źródła
DROP_RATIO = Decimal("0.15")  # dopisek o progu: główne źródło niższe o > 15%
OUTSIDE_POOL = {"savings", "income", "excluded"}  # grupy ostatniej transakcji: seria poza pulą
POOL_INCOME = {"wynagrodzenie", "swiadczenia"}  # podkategorie przychodów zasilające pulę


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
class IncomeSource:
    name: str
    amount: Decimal  # wpływy w miesiącu bazowym
    bonus: Decimal = ZERO  # część poza pulą


@dataclass
class FixedLine:
    category: Category
    parent: str  # nazwa kategorii głównej
    median: Decimal  # mediana miesięczna z historii (wydatek dodatni)


@dataclass
class SeriesLine:
    series: Series
    monthly: Decimal  # oczekiwana kwota w przeliczeniu na miesiąc


@dataclass
class Pool:
    """Serie liczone w puli: ich transakcje są pomijane w „wydane”, medianach i „poza pulą”."""

    lines: list[SeriesLine] = field(default_factory=list)
    txns: list[S.Candidate] = field(default_factory=list)

    @property
    def skip(self) -> set[int]:
        return {t.id for t in self.txns}


@dataclass
class AutoBudget:
    """Pula z dochodu: wpływy z `income_month` − premie − stałe (nie poniżej 0)."""

    income_month: date
    income: Decimal
    bonus: Decimal
    fixed: Decimal  # suma `series_lines` i `fixed_lines`
    fixed_months: int
    sources: list[IncomeSource] = field(default_factory=list)
    series_lines: list[SeriesLine] = field(default_factory=list)  # serie cykliczne
    fixed_lines: list[FixedLine] = field(default_factory=list)  # podkategorie stałe spoza serii
    candidates: list[FixedLine] = field(default_factory=list)  # pozostałe wydatkowe, do „dodaj”
    drop: tuple[str, float] | None = None  # (główne źródło, spadek) — dopisek o progu

    @property
    def amount(self) -> Decimal:
        return max(self.income - self.bonus - self.fixed, ZERO)

    @property
    def fixed_series(self) -> Decimal:
        return sum((line.monthly for line in self.series_lines), ZERO)


@dataclass
class FlexMonth:
    month: date
    prev_month: date
    next_month: date | None  # None, gdy następny miesiąc jeszcze się nie zaczął
    budget: Decimal | None  # ręczna albo automatyczna; None — brak obu
    budget_from: date | None  # od którego miesiąca obowiązuje kwota ręczna
    spent: Decimal  # elastyczne netto + bez kategorii
    uncategorized: Decimal
    uncategorized_count: int
    fixed: Decimal  # informacyjnie
    non_monthly: Decimal  # informacyjnie
    recurring: Decimal  # informacyjnie: zapłacone w miesiącu z serii liczonych w puli
    days_in_month: int
    day: int | None  # dzisiejszy dzień miesiąca; None dla miesięcy minionych
    lines: list[FlexLine] = field(default_factory=list)
    history: list[HistoryMonth] = field(default_factory=list)
    other_currency: int = 0
    budget_source: str | None = None  # "manual" | "auto" | None
    auto: AutoBudget | None = None  # pula z dochodu (także przy ręcznej — informacyjnie)

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


def budget_for(conn: sqlite3.Connection, month: date) -> tuple[Decimal | None, date] | None:
    """Wpis obowiązujący w miesiącu i miesiąc, od którego obowiązuje (kwota None = auto)."""
    row = conn.execute(
        "SELECT month_from, amount FROM flex_budget WHERE month_from <= ? "
        "ORDER BY month_from DESC LIMIT 1",
        (month_start(month).isoformat(),),
    ).fetchone()
    if row is None:
        return None
    amount = Decimal(row["amount"]) if row["amount"] is not None else None
    return amount, date.fromisoformat(row["month_from"])


def parse_amount(value: str) -> Decimal:
    try:
        amount = money.parse(value)
    except money.AmountError:
        amount = None
    if amount is None or amount <= 0 or amount >= BUDGET_MAX:
        raise FlexError("Podaj kwotę budżetu większą od zera, np. 2500 albo 2 500,00.")
    return amount


def set_budget(conn: sqlite3.Connection, month: date, amount: Decimal | None) -> None:
    """Kwota od miesiąca `month` (do następnej zmiany); None = pula automatyczna."""
    conn.execute(
        "INSERT INTO flex_budget (month_from, amount, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (month_from) DO UPDATE SET amount = excluded.amount, "
        "updated_at = excluded.updated_at",
        (
            month_start(month).isoformat(),
            money.fmt(amount) if amount is not None else None,
            now_iso(),
        ),
    )


# --- wyliczenie -------------------------------------------------------------------------------


def first_month(conn: sqlite3.Connection) -> date | None:
    row = conn.execute(
        "SELECT min(coalesce(t.tx_date, t.booking_date)) FROM txn t "
        "JOIN account a ON a.id = t.account_id "
        "WHERE t.status = 'BOOK' AND a.include_in_budget = 1 AND t.currency = ?",
        (BASE_CURRENCY,),
    ).fetchone()
    return month_start(date.fromisoformat(row[0][:10])) if row and row[0] else None


def pool_series(snap: Snapshot) -> Pool:
    """Aktywne serie wydatkowe liczone w puli (reguła: ostatnia transakcja nie z grup poza pulą)."""
    live = [s for s in S.all_series(snap.conn, ("active",)) if s.direction == "out"]
    if not live:
        return Pool()
    members = S.assign(live, snap.candidates())
    groups = {i: c.flex_group for i, c in taxonomy.leaves(snap.conn).items()}
    pool = Pool()
    for s in live:
        txns = members.get(s.id, [])
        if txns and groups.get(txns[-1].category_id or 0) in OUTSIDE_POOL:
            continue
        pool.lines.append(SeriesLine(s, s.monthly))
        pool.txns += txns
    pool.lines.sort(key=lambda line: (-line.monthly, line.series.name))
    return pool


def _history(
    conn: sqlite3.Connection, start: date, skip: set[int] | None = None
) -> list[tuple[date, Sums]]:
    """Pełne miesiące przed `start` (najwyżej `HISTORY_MONTHS`), od pierwszej transakcji."""
    first = first_month(conn)
    if first is None:
        return []
    out = []
    for n in range(HISTORY_MONTHS, 0, -1):
        m = add_months(start, -n)
        if m >= first:
            out.append((m, sums(conn, m, add_months(m, 1), skip or ())))
    return out


def _spent(s: Sums, flexible: list[Category]) -> Decimal:
    net = sum((s.by_leaf[c.id].amount for c in flexible if c.id in s.by_leaf), ZERO)
    return s.unc_out.amount - net  # kwoty wydatków są ujemne


def _group(s: Sums, leaves: list[Category], group: str) -> Decimal:
    return -sum(
        (s.by_leaf[c.id].amount for c in leaves if c.flex_group == group and c.id in s.by_leaf),
        ZERO,
    )


def _medians(
    conn: sqlite3.Connection, history: list[tuple[date, Sums]], groups: set[str], include: bool
) -> list[FixedLine]:
    """Mediany wydatków podkategorii z grup `groups` (albo spoza nich); tylko > 0, malejąco."""
    parents = {m.category.id: m.category.name for m in taxonomy.tree(conn)}
    out = []
    for c in taxonomy.leaves(conn).values():
        if (c.flex_group in groups) != include:
            continue
        past = [-s.by_leaf[c.id].amount if c.id in s.by_leaf else ZERO for _, s in history]
        median = Decimal(statistics.median(past)).quantize(money.CENT) if past else ZERO
        if median > 0:
            out.append(FixedLine(c, parents.get(c.parent_id or 0, ""), median))
    out.sort(key=lambda line: (-line.median, line.category.name))
    return out


def _income_by_source(
    conn: sqlite3.Connection, start: date, end: date
) -> dict[str, dict[date, Decimal]]:
    """Wpływy z podkategorii `POOL_INCOME` per źródło i miesiąc (filtry jak w `spending`)."""
    income = {
        i
        for i, c in taxonomy.leaves(conn).items()
        if c.flex_group == "income" and c.slug in POOL_INCOME
    }
    rows = conn.execute(
        "SELECT coalesce(t.tx_date, t.booking_date) AS day, t.amount, t.category_id, "
        "coalesce(nullif(t.merchant, ''), nullif(t.counterparty_name, ''), "
        "nullif(t.description, ''), '?') AS source "
        "FROM txn t JOIN account a ON a.id = t.account_id "
        "WHERE t.status = 'BOOK' AND t.transfer_group IS NULL AND a.include_in_budget = 1 "
        "AND t.currency = ? AND t.category_id IS NOT NULL "
        "AND coalesce(t.tx_date, t.booking_date) >= ? AND coalesce(t.tx_date, t.booking_date) < ?",
        (BASE_CURRENCY, start.isoformat(), end.isoformat()),
    ).fetchall()
    out: dict[str, dict[date, Decimal]] = {}
    for r in rows:
        if r["category_id"] in income:
            m = month_start(date.fromisoformat(r["day"][:10]))
            by_month = out.setdefault(str(r["source"]), {})
            by_month[m] = by_month.get(m, ZERO) + Decimal(r["amount"])
    return out


def _bonus_limit(values: list[Decimal]) -> Decimal | None:
    """Granica premii z historii źródła; None — za krótka historia."""
    if len(values) < BONUS_MIN_MONTHS:
        return None
    q3 = Decimal(statistics.quantiles(values, n=4, method="inclusive")[2])
    return BONUS_RATIO * q3


def auto_budget(
    snap: Snapshot,
    month: date,
    history: list[tuple[date, Sums]] | None = None,
    pool: Pool | None = None,
) -> AutoBudget | None:
    """Pula z dochodu na miesiąc `month`; None — brak wpływów w poprzednim miesiącu."""
    conn = snap.conn
    start = month_start(month)
    base = add_months(start, -1)
    window = [add_months(base, -n) for n in range(BONUS_WINDOW, 0, -1)]
    data = _income_by_source(conn, window[0], start)
    sources = []
    for name in sorted(data):
        amount = data[name].get(base, ZERO)
        if amount <= 0:
            continue
        past = [data[name][m] for m in window if data[name].get(m, ZERO) > 0]
        limit = _bonus_limit(past)
        bonus = ZERO
        if limit is not None and amount > limit:
            typical = Decimal(statistics.median(past[-BONUS_TYPICAL_MONTHS:]))
            bonus = (amount - typical).quantize(money.CENT)
        sources.append(IncomeSource(name, amount, bonus))
    if not sources:
        return None
    if pool is None:
        pool = pool_series(snap)
    if history is None:
        history = _history(conn, start, pool.skip)
    fixed_lines = _medians(conn, history, {"fixed"}, include=True)
    out = AutoBudget(
        income_month=base,
        income=sum((s.amount for s in sources), ZERO),
        bonus=sum((s.bonus for s in sources), ZERO),
        fixed=sum((line.median for line in fixed_lines), ZERO)
        + sum((line.monthly for line in pool.lines), ZERO),
        fixed_months=len(history),
        sources=sources,
        series_lines=pool.lines,
        fixed_lines=fixed_lines,
        candidates=_medians(conn, history, {"fixed", "income"}, include=False),
    )
    out.drop = _drop(data, base, sources)
    return out


def _drop(
    data: dict[str, dict[date, Decimal]], base: date, sources: list[IncomeSource]
) -> tuple[str, float] | None:
    """Główne źródło niższe niż zwykle w tym roku (bez miesięcy z premią) — dopisek o progu."""
    main = max(data, key=lambda name: sum(data[name].values()))
    current = next((s for s in sources if s.name == main and not s.bonus), None)
    if current is None:
        return None
    year = [v for m, v in sorted(data[main].items()) if m.year == base.year and m < base and v > 0]
    limit = _bonus_limit(year)
    if limit is not None:
        year = [v for v in year if v <= limit]
    if len(year) < 2:
        return None
    usual = Decimal(statistics.median(year))
    if current.amount >= usual * (1 - DROP_RATIO):
        return None
    return main, float(1 - current.amount / usual)


def build(snap: Snapshot, month: date, today: date) -> FlexMonth:
    conn = snap.conn
    start = month_start(month)
    nxt = add_months(start, 1)
    pool = pool_series(snap)
    skip = pool.skip
    cur = sums(conn, start, nxt, skip)
    history = _history(conn, start, skip)
    parents = {m.category.id: m.category.name for m in taxonomy.tree(conn)}
    leaves = list(taxonomy.leaves(conn).values())
    flexible = [c for c in leaves if c.flex_group == "flexible"]
    current = start == month_start(today)
    manual = budget_for(conn, start)
    if manual is not None and manual[0] is None:
        manual = None  # wpis „wróć do automatycznej”
    auto = auto_budget(snap, start, history, pool)

    out = FlexMonth(
        month=start,
        prev_month=add_months(start, -1),
        next_month=nxt if nxt <= today else None,
        budget=manual[0] if manual else (auto.amount if auto else None),
        budget_from=manual[1] if manual else None,
        spent=_spent(cur, flexible),
        uncategorized=cur.unc_out.amount,
        uncategorized_count=cur.unc_out.count,
        fixed=_group(cur, leaves, "fixed"),
        non_monthly=_group(cur, leaves, "non_monthly"),
        recurring=sum((abs(t.amount) for t in pool.txns if start <= t.day < nxt), ZERO),
        days_in_month=calendar.monthrange(start.year, start.month)[1],
        day=today.day if current else None,
        history=[HistoryMonth(m, _spent(s, flexible), s.unc_out.amount) for m, s in history],
        other_currency=cur.other_currency,
        budget_source="manual" if manual else ("auto" if auto else None),
        auto=auto,
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
