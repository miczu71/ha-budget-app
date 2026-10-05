"""Geometria wykresów Podsumowania (M13 E2): czyste funkcje, bez HTTP i bez szablonów.

SVG składają makra w `_charts.html`; kolory to klasy CSS (`c1`…`c8`, `other`, `unc`) rozwiązywane
przez tokeny motywu, więc kod nic nie wie o palecie.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from budget.spending import MainLine, MonthTotals

PALETTE = 8  # liczba kolorów kategorii w tokenach `--chart-1…8`
ZERO = Decimal(0)
MONTH_ABBR = ("sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru")


@dataclass(frozen=True)
class Slice:
    key: str  # `cat-<id>`, `other`, `unc`
    label: str
    amount: Decimal
    count: int
    pct: int  # udział w %, zaokrąglony tak, że całość daje 100
    color: str  # klasa CSS: c1…c8, other, unc
    start: float  # początek łuku na obwodzie 0..100 (`pathLength="100"`), już z połową odstępu
    length: float  # długość widocznego łuku (po odjęciu odstępu)
    href: str  # ścieżka panelu bez prefiksu Ingress

    @property
    def dash(self) -> str:
        return f"{self.length:.3f} {100 - self.length:.3f}"

    @property
    def offset(self) -> str:
        return f"{-self.start:.3f}"


def _percentages(shares: Sequence[float]) -> list[int]:
    """Procenty całkowite metodą największej reszty (suma 100, gdy udziały sumują się do 1)."""
    raw = [s * 100 for s in shares]
    out = [int(r) for r in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True)[
        : max(100 - sum(out), 0)
    ]:
        out[i] += 1
    return out


def donut_slices(
    groups: Sequence[MainLine],
    uncategorized: Decimal,
    uncategorized_count: int,
    *,
    period: str,
    other_href: str,
    review_href: str,
    top: int = 6,
    gap: float = 0.8,
) -> list[Slice]:
    """Wycinki wykresu kołowego wydatków: `top` największych kategorii, „Inne”, „Bez kategorii”.

    Tylko kwoty dodatnie (zwrot netto nie tworzy wycinka); udziały liczone od ich sumy.
    Kolor kategorii jest stały (`id % PALETTE`), a kolizja w obrębie jednego wykresu przesuwa
    mniejszy wycinek na następny wolny kolor.
    """
    positive = sorted((g for g in groups if g.amount > ZERO), key=lambda g: g.amount, reverse=True)
    uncategorized = max(uncategorized, ZERO)
    total = sum((g.amount for g in positive), ZERO) + uncategorized
    if total <= ZERO:
        return []

    used: set[int] = set()
    parts: list[
        tuple[str, str, Decimal, int, str, str]
    ] = []  # key, label, kwota, liczba, kolor, href
    for g in positive[:top]:
        slot = g.category.id % PALETTE
        while slot in used:
            slot = (slot + 1) % PALETTE
        used.add(slot)
        href = f"/transactions?category={g.category.id}&{period}"
        parts.append(
            (f"cat-{g.category.id}", g.category.name, g.amount, g.count, f"c{slot + 1}", href)
        )
    rest = positive[top:]
    if rest:
        amount = sum((g.amount for g in rest), ZERO)
        parts.append(("other", "Inne", amount, sum(g.count for g in rest), "other", other_href))
    if uncategorized > ZERO:
        parts.append(
            ("unc", "Bez kategorii", uncategorized, uncategorized_count, "unc", review_href)
        )

    shares = [float(p[2] / total) for p in parts]
    pcts = _percentages(shares)
    slices: list[Slice] = []
    cursor = 0.0
    for (key, label, amount, count, color, href), share, pct in zip(
        parts, shares, pcts, strict=True
    ):
        span = share * 100
        # jeden wycinek = pełny okrąg bez odstępu; inaczej odstęp po obu stronach łuku
        length = 100.0 if len(parts) == 1 else max(span - gap, 0.2)
        start = cursor + (0.0 if len(parts) == 1 else gap / 2)
        slices.append(Slice(key, label, amount, count, pct, color, start, length, href))
        cursor += span
    return slices


# --- słupki 12 miesięcy -----------------------------------------------------------------------

WIDTH, HEIGHT = 320, 170
# etykiety osi Y leżą w obszarze wykresu, więc słupek ma ≥ 24 px na telefonie
LEFT, RIGHT, TOP, BOTTOM = 4, 4, 8, 22
BAR_W, BAR_GAP = 8.0, 1.5


@dataclass(frozen=True)
class Bar:
    month: date
    label: str
    income: Decimal
    expenses: Decimal
    x: float  # lewa krawędź pary słupków
    slot_x: float  # lewa krawędź kolumny (tło zaznaczenia i pole klikalne)
    slot_w: float
    income_h: float
    expenses_h: float
    selected: bool
    partial: bool
    href: str  # ścieżka panelu bez prefiksu Ingress


@dataclass(frozen=True)
class Tick:
    label: str
    y: float


@dataclass(frozen=True)
class BarChart:
    bars: list[Bar]
    ticks: list[Tick]
    width: int = WIDTH
    height: int = HEIGHT
    bar_w: float = BAR_W
    baseline: float = HEIGHT - BOTTOM
    plot_left: float = LEFT
    plot_right: float = WIDTH - RIGHT

    @property
    def has_data(self) -> bool:
        return any(b.income or b.expenses for b in self.bars)


def nice_ceiling(value: float, floor: float = 1.0) -> float:
    """Najmniejsza „ładna” wartość (1, 2, 2,5, 5 × 10^k) nie mniejsza niż `value` i `floor`."""
    value = max(value, floor)
    base = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * base:
            return float(step * base)
    return float(10 * base)


def _compact(value: float) -> str:
    return f"{value / 1000:g}k" if value >= 1000 else f"{value:g}"


def month_bars(rows: Sequence[MonthTotals], selected: date) -> BarChart:
    """Pary słupków (wpływy, wydatki) dla kolejnych miesięcy; skala wspólna, z „ładnym” maksimum."""
    plot_h = HEIGHT - TOP - BOTTOM
    top = nice_ceiling(max((float(max(r.income, r.expenses)) for r in rows), default=0.0))
    slot = (WIDTH - RIGHT - LEFT) / max(len(rows), 1)
    pair = 2 * BAR_W + BAR_GAP

    def height(value: Decimal) -> float:
        return max(float(value) / top * plot_h, 1.0) if value > ZERO else 0.0

    bars = [
        Bar(
            month=r.month,
            label=MONTH_ABBR[r.month.month - 1],
            income=r.income,
            expenses=r.expenses,
            x=LEFT + i * slot + (slot - pair) / 2,
            slot_x=LEFT + i * slot,
            slot_w=slot,
            income_h=height(r.income),
            expenses_h=height(r.expenses),
            selected=r.month == selected,
            partial=r.partial,
            href=f"/?month={r.month:%Y-%m}",
        )
        for i, r in enumerate(rows)
    ]
    ticks = [Tick(_compact(v), HEIGHT - BOTTOM - v / top * plot_h) for v in (0.0, top / 2, top)]
    return BarChart(bars, ticks)
