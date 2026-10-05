"""Terminy i statusy serii w miesiącu (M5b E2): co zapłacone, co jeszcze zejdzie / wpłynie.

Czysta logika na wynikach `series.assign` — bez zapytań do bazy. Liczą się tylko serie
aktywne. Termin serii miesięcznej to `anchor_day` (obcięty do długości miesiąca); kwartalnej
i rocznej — ostatnie wystąpienie przed miesiącem plus wielokrotność kadencji (seria bez
wystąpień Q/Y nie ma terminu). Transakcja należy do najbliższego terminu w promieniu
`MATCH_DAYS` (terminy sąsiednich miesięcy też się liczą, więc płatność 30. na termin 1. trafia
do miesiąca terminu); poza promieniem jest „dodatkowa” i tylko zwiększa „zapłacone” miesiąca,
w którym padła.

Status terminu: zapłacone (jest transakcja), oczekiwane (do `WINDOW` dni po terminie),
spóźnione (później, miesiąc bieżący albo przyszły) i brak płatności (miesiąc już minął).
Spóźnione nadal liczą się do „jeszcze zejdzie / wpłynie”; brak płatności w minionym
miesiącu — nie.
"""

from __future__ import annotations

import calendar
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from budget import money
from budget.recurring import series as S
from budget.recurring.series import Candidate, Series
from budget.spending import add_months, month_start

WINDOW = 5  # dni po terminie, zanim płatność jest spóźniona
MATCH_DAYS = 15  # transakcja dalej niż tyle dni od każdego terminu jest „dodatkowa”
STEP = {"M": 1, "Q": 3, "Y": 12}

PAID, EXPECTED, LATE, MISSING, EXTRA = "paid", "expected", "late", "missing", "extra"
STATUS_LABELS = {
    PAID: "zapłacone",
    EXPECTED: "oczekiwane",
    LATE: "spóźnione",
    MISSING: "brak płatności",
    EXTRA: "dodatkowa",
}


@dataclass(frozen=True)
class Due:
    series: Series
    due: date | None  # None = dodatkowa płatność bez terminu
    status: str
    txns: tuple[Candidate, ...] = ()

    @property
    def paid_amount(self) -> Decimal:
        return sum((abs(t.amount) for t in self.txns), Decimal(0)).quantize(money.CENT)

    @property
    def sort_day(self) -> date:
        return self.due or self.txns[0].day


@dataclass
class MonthView:
    month: date
    rows: list[Due] = field(default_factory=list)

    def _sum(self, direction: str, statuses: tuple[str, ...], *, actual: bool) -> Decimal:
        total = Decimal(0)
        for d in self.rows:
            if d.series.direction == direction and d.status in statuses:
                total += d.paid_amount if actual else d.series.expected_amount
        return total.quantize(money.CENT)

    @property
    def out_paid(self) -> Decimal:
        return self._sum("out", (PAID, EXTRA), actual=True)

    @property
    def out_planned(self) -> Decimal:
        return self._sum("out", (EXPECTED, LATE), actual=False)

    @property
    def in_received(self) -> Decimal:
        return self._sum("in", (PAID, EXTRA), actual=True)

    @property
    def in_planned(self) -> Decimal:
        return self._sum("in", (EXPECTED, LATE), actual=False)

    def count(self, status: str) -> int:
        return sum(1 for d in self.rows if d.status == status)


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(max(day, 1), calendar.monthrange(year, month)[1]))


def due_date(s: Series, members: Sequence[Candidate], month: date) -> date | None:
    """Termin serii w miesiącu `month` (pierwszy dzień) albo None, gdy w tym miesiącu go nie ma."""
    if s.cadence == "M":
        return _clamped(month.year, month.month, s.anchor_day or 1)
    end = add_months(month, 1)
    ref = max((t.day for t in members if t.day < end), default=None)
    if ref is None:
        return None
    diff = (month.year * 12 + month.month) - (ref.year * 12 + ref.month)
    if diff < 0 or diff % STEP[s.cadence]:
        return None
    return _clamped(month.year, month.month, ref.day)


def _status(due: date, today: date, month: date) -> str:
    if due + timedelta(days=WINDOW) >= today:
        return EXPECTED
    return LATE if month_start(today) <= month else MISSING


def month_view(
    series: Sequence[Series],
    members: Mapping[int, Sequence[Candidate]],
    month: date,
    today: date,
) -> MonthView:
    """Terminy aktywnych serii w miesiącu `month` ze statusami, po dacie terminu."""
    month = month_start(month)
    nxt = add_months(month, 1)
    view = MonthView(month)
    for s in series:
        if s.status != "active":
            continue
        txns = members.get(s.id, [])
        dues = {m: due_date(s, txns, m) for m in (add_months(month, -1), month, nxt)}
        taken: dict[date, list[Candidate]] = {d: [] for d in dues.values() if d is not None}
        extras: list[Candidate] = []
        for t in txns:
            near = min(taken, key=lambda d: abs((d - t.day).days), default=None)
            if near is not None and abs((near - t.day).days) <= MATCH_DAYS:
                taken[near].append(t)
            elif month <= t.day < nxt:
                extras.append(t)
        due = dues[month]
        if due is not None:
            paid = tuple(taken[due])
            status = PAID if paid else _status(due, today, month)
            view.rows.append(Due(s, due, status, paid))
        if extras:
            view.rows.append(Due(s, None, EXTRA, tuple(extras)))
    view.rows.sort(key=lambda d: (d.sort_day, d.series.name))
    return view


def for_month(conn: sqlite3.Connection, month: date, today: date) -> MonthView:
    """Widok miesiąca z bazy: aktywne serie + przynależność liczona od zera."""
    all_series = S.all_series(conn, ("active",))
    members = S.assign(all_series, S.candidates(conn)) if all_series else {}
    return month_view(all_series, members, month, today)
