"""Detektor serii: propozycje płatności cyklicznych z historii księgi (bez LLM).

Grupa = (sprzedawca, kierunek) — raty kredytu (typ `loan`, opis inny co ratę) po (typ, konto,
kierunek) — wśród kandydatów (`series.candidates`) nieobjętych żadną
serią. Grupa, dla której istnieje seria w dowolnym statusie (także odrzucona), nie jest
proponowana ponownie.

Kadencja z mediany odstępów między wystąpieniami (ostatnie `MAX_GAPS`): co najmniej
`IN_WINDOW` odstępów musi mieścić się w oknie kadencji. Kwota musi być powtarzalna — co
najmniej `IN_WINDOW` z ostatnich `AMOUNT_TAIL` kwot w granicach `AMOUNT_SPREAD` od mediany
(zakupy u tego samego sprzedawcy raz w miesiącu to nie seria); seria roczna ma najwyżej dwa
wystąpienia w historii, więc jej kwoty muszą się zgadzać w granicach `MIN_TOLERANCE_PCT`.
Proponowane są tylko serie żywe: ostatnie wystąpienie nie starsze niż górna granica okna
+ `ALIVE_SLACK`.
"""

from __future__ import annotations

import sqlite3
import statistics
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import pairwise

from budget import money
from budget.categorize.rules import Conditions, TextCondition
from budget.ledger import transaction
from budget.recurring import series as S
from budget.recurring.series import Candidate

WINDOWS = {"M": (26, 35), "Q": (80, 100), "Y": (350, 380)}
MONTH_STEPS = {"M": (1,), "Q": (3,), "Y": (11, 12, 13)}  # odstęp w miesiącach kalendarzowych
LOAN = "loan"  # raty kredytu: opis zmienia się co ratę — grupa po typie i koncie
LOAN_NAME = "Rata kredytu"
MIN_OCCURRENCES = {"M": 3, "Q": 3, "Y": 2}
ALIVE_SLACK = 10  # dni po górnej granicy okna
MAX_GAPS = 12
IN_WINDOW = 0.7
AMOUNT_TAIL = 6
AMOUNT_SPREAD = Decimal("0.35")
MIN_TOLERANCE_PCT = Decimal("0.10")
MIN_TOLERANCE = Decimal("5.00")


@dataclass(frozen=True)
class Proposal:
    key: str
    name: str
    conditions: Conditions
    direction: str
    cadence: str
    expected: Decimal
    tolerance: Decimal
    anchor_day: int
    occurrences: int
    last: date


def _median_decimal(values: Sequence[Decimal]) -> Decimal:
    return Decimal(statistics.median(values)).quantize(money.CENT)


def _cadence(days: Sequence[date]) -> str | None:
    """Odstęp pasuje do kadencji, gdy mieści się w oknie dni albo wypada w miesiącu
    o właściwym numerze (płatność „w miesiącu” raz 1., raz 7. dnia to wciąż co miesiąc)."""
    pairs = list(pairwise(days))[-MAX_GAPS:]
    if not pairs:
        return None
    for cadence, (lo, hi) in WINDOWS.items():
        if len(days) < MIN_OCCURRENCES[cadence]:
            continue
        fits = sum(
            lo <= (b - a).days <= hi
            or (b.year * 12 + b.month) - (a.year * 12 + a.month) in MONTH_STEPS[cadence]
            for a, b in pairs
        )
        if fits >= IN_WINDOW * len(pairs):
            return cadence
    return None


def _group(txns: Sequence[Candidate], key: str, today: date) -> Proposal | None:
    # kilka transakcji jednego dnia (np. dwie raty) — jedno wystąpienie o łącznej kwocie
    per_day: dict[date, Decimal] = defaultdict(Decimal)
    for t in txns:
        per_day[t.day] += abs(t.amount)
    days = sorted(per_day)
    cadence = _cadence(days)
    if cadence is None:
        return None
    if (today - days[-1]).days > WINDOWS[cadence][1] + ALIVE_SLACK:
        return None
    tail = [per_day[d] for d in days[-AMOUNT_TAIL:]]
    expected = _median_decimal(tail)
    band = (MIN_TOLERANCE_PCT if cadence == "Y" else AMOUNT_SPREAD) * expected
    close = [a for a in tail if abs(a - expected) <= band]
    if len(close) < IN_WINDOW * len(tail):
        return None
    # rozrzut tylko z kwot typowych — premia czy jednorazowa dopłata nie poszerza tolerancji
    spread = max((abs(a - expected) for a in close), default=Decimal(0))
    tolerance = max(expected * MIN_TOLERANCE_PCT, MIN_TOLERANCE, spread).quantize(money.CENT)
    last = txns[-1]
    if last.facts.kind == LOAN:
        name = LOAN_NAME
        cond = Conditions(kind=LOAN, account_id=last.facts.account_id, direction=last.direction)
    else:
        name = last.merchant[: S.NAME_MAX]
        cond = Conditions(
            text=(TextCondition("merchant", "equals", last.facts.merchant),),
            direction=last.direction,
        )
    anchor = (
        int(statistics.median_low([d.day for d in days[-AMOUNT_TAIL:]]))
        if cadence == "M"
        else days[-1].day
    )
    return Proposal(
        key=key,
        name=name,
        conditions=cond,
        direction=last.direction,
        cadence=cadence,
        expected=expected,
        tolerance=tolerance,
        anchor_day=anchor,
        occurrences=len(days),
        last=days[-1],
    )


def find(
    txns: Sequence[Candidate], today: date, *, blocked: Collection[str], covered: Collection[int]
) -> list[Proposal]:
    """Propozycje serii (czysta funkcja), od największej kwoty miesięcznej."""
    groups: dict[str, list[Candidate]] = defaultdict(list)
    for t in txns:
        if t.id in covered or not t.amount:
            continue
        if t.facts.kind == LOAN:
            groups[f"kind:{LOAN}:{t.facts.account_id}|{t.direction}"].append(t)
        elif t.facts.merchant.strip():
            groups[S.group_key(t.facts.merchant, t.direction)].append(t)
    out = []
    for key, items in groups.items():
        if key in blocked:
            continue
        if (p := _group(items, key, today)) is not None:
            out.append(p)
    div = {"M": 1, "Q": 3, "Y": 12}
    out.sort(key=lambda p: (-p.expected / div[p.cadence], p.name))
    return out


def run(conn: sqlite3.Connection, today: date) -> list[Proposal]:
    """Nowe propozycje zapisane jako `proposed`; zwraca dodane."""
    existing = S.all_series(conn)
    txns = S.candidates(conn)
    members = S.assign(existing, txns)
    blocked = {s.group_key for s in existing if s.group_key}
    found = find(txns, today, blocked=blocked, covered=S.covered_ids(members))
    with transaction(conn):
        for p in found:
            S.insert(
                conn,
                name=p.name,
                direction=p.direction,
                cadence=p.cadence,
                conditions=p.conditions,
                expected=p.expected,
                tolerance=p.tolerance,
                anchor_day=p.anchor_day,
                status="proposed",
                origin="detected",
                key=p.key,
            )
    return found
