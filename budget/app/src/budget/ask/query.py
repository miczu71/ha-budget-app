"""Język zapytań czatu (M12): plan od LLM → walidacja → wynik liczony lokalnie.

Zbiór transakcji i znaki kwot jak na ekranie „Wydatki” (`spending._rows`, `spending.section`):
zaksięgowane, bez przelewów między własnymi kontami, konta w budżecie, PLN (inne waluty liczone
osobno). Wydatki są dodatnie i netto (zwrot zmniejsza kategorię), wpływy dodatnie.

Prywatność (decyzja 23): nazwa w wierszu pogrupowanym po sprzedawcy idzie do LLM tylko wtedy,
gdy wszystkie jego transakcje w wyniku to karta/BLIK; inaczej etykieta `[O1]`, `[O2]`… (nawias,
bo polskie „Odbiorca 1” model odmienia i podmiana by nie trafiła).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from budget.categorize import taxonomy
from budget.categorize.taxonomy import FLEX_LABELS, Category
from budget.kinds import CARD_KINDS
from budget.money import CENT
from budget.normalize import fold, matches_all, search_words
from budget.spending import (
    BASE_CURRENCY,
    ZERO,
    _rows,
    add_months,
    month_label,
    month_start,
    section,
)

MAX_MONTHS = 60
MAX_LIMIT = 50
SCOPES = ("expenses", "income", "savings", "excluded")
SCOPE_LABELS = {"expenses": "wydatki", "income": "wpływy"} | {s: FLEX_LABELS[s] for s in SCOPES[2:]}
EXPENSE_GROUPS = ("fixed", "flexible", "non_monthly")
GROUP_BY = ("none", "month", "category", "main_category", "merchant")
GROUP_BY_LABELS = {
    "month": "miesiące",
    "category": "podkategorie",
    "main_category": "kategorie główne",
    "merchant": "sprzedawcy i odbiorcy",
}
METRICS = ("sum", "count", "avg_per_month")
METRIC_LABELS = {"sum": "suma", "count": "liczba transakcji", "avg_per_month": "średnio na miesiąc"}
NO_CATEGORY = "Bez kategorii"
NO_NAME = "(bez nazwy)"

_MONTH = {"type": "string", "description": "RRRR-MM"}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "unsupported": {"type": "string"},
        "periods": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"from": _MONTH, "to": _MONTH},
                "required": ["from", "to"],
                "additionalProperties": False,
            },
        },
        "scope": {"type": "string", "enum": list(SCOPES)},
        "categories": {"type": "array", "items": {"type": "integer"}},
        "exclude_categories": {"type": "array", "items": {"type": "integer"}},
        "flex_groups": {"type": "array", "items": {"type": "string", "enum": list(EXPENSE_GROUPS)}},
        "text": {"type": "string"},
        "group_by": {"type": "string", "enum": list(GROUP_BY)},
        "metric": {"type": "string", "enum": list(METRICS)},
        "limit": {"type": "integer"},
    },
    "required": [
        "unsupported",
        "periods",
        "scope",
        "categories",
        "exclude_categories",
        "flex_groups",
        "text",
        "group_by",
        "metric",
        "limit",
    ],
    "additionalProperties": False,
}


class PlanError(ValueError):
    """Plan od LLM nie do wykonania — komunikat dla użytkownika."""


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


@dataclass(frozen=True)
class Period:
    start: date  # pierwszy dzień miesiąca
    end: date  # pierwszy dzień miesiąca po okresie (bez niego)

    @property
    def months(self) -> int:
        return _months_between(self.start, self.end)

    @property
    def label(self) -> str:
        last = add_months(self.end, -1)
        if last == self.start:
            return month_label(self.start)
        return f"{month_label(self.start)} – {month_label(last)}"


@dataclass(frozen=True)
class Plan:
    periods: tuple[Period, ...]
    scope: str
    categories: tuple[int, ...]  # id z planu (główne albo podkategorie)
    exclude: tuple[int, ...]  # jak wyżej — wykluczone („bez paliwa”, M12 E2)
    flex_groups: tuple[str, ...]
    text: str
    group_by: str
    metric: str
    limit: int


def _month(value: Any) -> date:
    try:
        y, m = str(value).split("-")
        return date(int(y), int(m), 1)
    except ValueError as exc:
        raise PlanError(f"nieprawidłowy miesiąc {value!r}") from exc


def parse(raw: dict[str, Any], cats: dict[int, Category], today: date) -> Plan:
    """Plan z odpowiedzi LLM; miesiące z przyszłości przycinane do bieżącego."""
    current = month_start(today)
    periods = []
    for p in (raw.get("periods") or [])[:2]:
        start, last = _month(p.get("from")), min(_month(p.get("to")), current)
        if start > current:
            raise PlanError("okres zaczyna się w przyszłości")
        if start > last:
            raise PlanError("okres kończy się przed początkiem")
        period = Period(start, add_months(last, 1))
        if period.months > MAX_MONTHS:
            raise PlanError(f"okres dłuższy niż {MAX_MONTHS} miesięcy")
        periods.append(period)
    if not periods:
        raise PlanError("brak okresu")

    def category_ids(key: str) -> tuple[int, ...]:
        ids = tuple(dict.fromkeys(int(i) for i in raw.get(key) or []))
        unknown = [i for i in ids if i not in cats]
        if unknown:
            raise PlanError(f"nieznane kategorie {unknown}")
        return ids

    def pick(key: str, allowed: tuple[str, ...]) -> str:
        value = str(raw.get(key) or allowed[0])
        if value not in allowed:
            raise PlanError(f"nieznana wartość {key}={value!r}")
        return value

    groups = tuple(dict.fromkeys(str(g) for g in raw.get("flex_groups") or []))
    if any(g not in EXPENSE_GROUPS for g in groups):
        raise PlanError(f"nieznane grupy {list(groups)}")
    limit = int(raw.get("limit") or 10)
    return Plan(
        periods=tuple(periods),
        scope=pick("scope", SCOPES),
        categories=category_ids("categories"),
        exclude=category_ids("exclude_categories"),
        flex_groups=groups,
        text=str(raw.get("text") or "").strip(),
        group_by=pick("group_by", GROUP_BY),
        metric=pick("metric", METRICS),
        limit=min(max(limit, 1), MAX_LIMIT),
    )


@dataclass
class Row:
    key: Any
    label: str  # prawdziwa nazwa (tylko lokalnie)
    amounts: list[Decimal]  # dla każdego okresu
    counts: list[int]
    private: bool = False  # odbiorca przelewu — do LLM tylko etykieta
    llm_label: str = ""
    values: list[Decimal] = field(default_factory=list)  # miara dla każdego okresu


@dataclass
class PeriodResult:
    period: Period
    value: Decimal = ZERO  # miara dla całego okresu
    count: int = 0
    partial: bool = False  # zawiera bieżący, niepełny miesiąc
    link: dict[str, str] = field(default_factory=dict)  # filtry ekranu Transakcje


@dataclass
class Result:
    plan: Plan
    periods: list[PeriodResult]
    rows: list[Row]
    filters: list[str]

    @property
    def labels(self) -> dict[str, str]:
        """Etykieta dla LLM → prawdziwa nazwa (tylko tam, gdzie się różnią)."""
        return {r.llm_label: r.label for r in self.rows if r.llm_label != r.label}

    def for_llm(self) -> dict[str, Any]:
        """Wynik zbiorczy po redakcji — jedyne dane z księgi, które idą do LLM."""
        return {
            "metric": self.plan.metric,
            "group_by": self.plan.group_by,
            "periods": [
                {
                    "period": p.period.label,
                    "months": p.period.months,
                    "value": str(p.value),
                    "transactions": p.count,
                    "current_month_incomplete": p.partial,
                }
                for p in self.periods
            ],
            "rows": [
                {"label": r.llm_label, "values": [str(v) for v in r.values]} for r in self.rows
            ],
            "filters": self.filters,
        }


def _expand(ids: tuple[int, ...], cats: dict[int, Category]) -> set[int]:
    out: set[int] = set()
    for i in ids:
        if cats[i].is_main:
            out |= {c.id for c in cats.values() if c.parent_id == i}
        else:
            out.add(i)
    return out


def _measure(metric: str, amount: Decimal, count: int, months: int) -> Decimal:
    if metric == "count":
        return Decimal(count)
    if metric == "avg_per_month":
        return (amount / months).quantize(CENT)
    return amount


def describe(plan: Plan, cats: dict[int, Category], other_currency: int = 0) -> list[str]:
    """„Jak policzono” — po polsku, bez danych z księgi."""
    out = ["Okres: " + " vs ".join(p.label for p in plan.periods)]
    if plan.categories:
        out.append("Kategorie: " + ", ".join(cats[i].name for i in plan.categories))
    else:
        out.append(f"Zakres: {SCOPE_LABELS[plan.scope]}")
    if plan.exclude:
        out.append("Bez kategorii: " + ", ".join(cats[i].name for i in plan.exclude))
    if plan.flex_groups:
        out.append("Grupy budżetu: " + ", ".join(FLEX_LABELS[g] for g in plan.flex_groups))
    if plan.text:
        out.append(f"Tekst w opisie, odbiorcy albo sprzedawcy: „{plan.text}”")
    if plan.group_by != "none":
        out.append(f"Podział: {GROUP_BY_LABELS[plan.group_by]}")
    out.append(f"Miara: {METRIC_LABELS[plan.metric]}")
    if other_currency:
        out.append(f"Pominięte transakcje w innej walucie: {other_currency}")
    return out


def execute(
    conn: sqlite3.Connection, plan: Plan, today: date, cats: dict[int, Category] | None = None
) -> Result:
    cats = cats if cats is not None else taxonomy.all_categories(conn)
    wanted = _expand(plan.categories, cats)
    excluded = _expand(plan.exclude, cats)
    words = search_words(plan.text)
    current = month_start(today)
    n_periods = len(plan.periods)
    periods: list[PeriodResult] = []
    groups: dict[Any, Row] = {}
    other_currency = 0
    for n, period in enumerate(plan.periods):
        res = PeriodResult(period, partial=period.end > current)
        last = min(period.end - timedelta(days=1), today)
        res.link = {"date_from": period.start.isoformat(), "date_to": last.isoformat()}
        if len(plan.categories) == 1:
            res.link["category"] = str(plan.categories[0])
        if plan.text:
            res.link["q"] = plan.text
        amount_total = ZERO
        for r in _rows(conn, period.start, period.end, details=True):
            amount = Decimal(r["amount"])
            leaf = cats.get(r["category_id"]) if r["category_id"] is not None else None
            sec = section(leaf, amount)
            if wanted:
                if leaf is None or leaf.id not in wanted:
                    continue
            elif sec != plan.scope:
                continue
            if leaf is not None and leaf.id in excluded:
                continue
            if plan.flex_groups and (leaf is None or leaf.flex_group not in plan.flex_groups):
                continue
            if words and not matches_all(
                fold(
                    f"{r['description'] or ''} {r['counterparty_name'] or ''} {r['merchant'] or ''}"
                ),
                words,
            ):
                continue
            if r["currency"] != BASE_CURRENCY:
                other_currency += 1
                continue
            value = amount if sec == "income" else -amount
            amount_total += value
            res.count += 1
            key, label = _key(plan.group_by, r, leaf, cats, period)
            if key is None:
                continue
            row = groups.get(key)
            if row is None:
                row = groups[key] = Row(key, label, [ZERO] * n_periods, [0] * n_periods)
            row.amounts[n] += value
            row.counts[n] += 1
            row.private |= plan.group_by == "merchant" and r["kind"] not in CARD_KINDS
        res.value = _measure(plan.metric, amount_total, res.count, period.months)
        periods.append(res)
    rows = list(groups.values())
    for row in rows:
        row.values = [
            _measure(plan.metric, a, c, p.period.months)
            for a, c, p in zip(row.amounts, row.counts, periods, strict=True)
        ]
    if plan.group_by == "month":
        rows.sort(key=lambda r: r.key)
        for row in rows:
            row.label = " / ".join(month_label(add_months(p.start, row.key)) for p in plan.periods)
    else:
        rows.sort(key=lambda r: (-r.values[0], -sum(r.values), r.label))
        rows = rows[: plan.limit]
    n_private = 0
    for row in rows:
        if row.private:
            n_private += 1
            row.llm_label = f"[O{n_private}]"
        else:
            row.llm_label = row.label
    return Result(plan, periods, rows, describe(plan, cats, other_currency))


def _key(
    group_by: str, r: sqlite3.Row, leaf: Category | None, cats: dict[int, Category], period: Period
) -> tuple[Any, str]:
    if group_by == "month":
        # przy porównaniu dwóch okresów wiersz = n-ty miesiąc każdego z nich (etykieta w `execute`)
        return _months_between(period.start, date.fromisoformat(r["day"])), ""
    if group_by == "category":
        return (leaf.id, leaf.name) if leaf else (0, NO_CATEGORY)
    if group_by == "main_category":
        if leaf is None or leaf.parent_id is None:
            return 0, NO_CATEGORY
        return leaf.parent_id, cats[leaf.parent_id].name
    if group_by == "merchant":
        name = r["merchant"] or r["counterparty_name"] or ""
        return name, name or NO_NAME
    return None, ""
