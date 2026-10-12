"""Prognoza „czy starczy do wypłaty” (M8 E1): wolne środki dzień po dniu do najbliższej wypłaty.

Wolne środki dziś = saldo rachunku PLN (dostępne, już bez autoryzacji) − bieżące zadłużenie karty.
Przyszłość: oczekiwane i spóźnione wydatki serii w ich terminach (spóźnione liczą się dziś),
reszta puli Flex po równo na dni, wpływy serii przed wypłatą. Wydatki zrobione dziś są już
w saldzie i zadłużeniu karty, więc Flex liczy się od jutra. Spóźniony wpływ nie jest
wypłatą ani nie zwiększa salda — nie wiadomo, kiedy dotrze. Wypłata = najbliższy termin aktywnej
serii wpływowej o największej oczekiwanej kwocie (mniejsze wpływy do dnia wypłaty włącznie wchodzą
do salda — jak wydatki tego dnia, M21);
bez takiej serii horyzont kończy się z miesiącem. Saldo na dzień wypłaty jest przed jej
wpłynięciem, bo tam leży dno. Termin wypłaty w miesiącu można przestawić ręcznie (M21 E1,
`schedule.set_override`).
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal

from budget import card, flex, ledger, money, piggy
from budget.recurring import schedule
from budget.snapshot import Snapshot
from budget.spending import add_months, month_start
from budget.storage import db

ZERO = Decimal(0)
EXTRA_MONTHS = 2  # ile następnych miesięcy sprawdzamy, gdy bieżący nie ma już wypłaty
STALE_AFTER = timedelta(hours=24)
PAYDAY_KEY = "payday_series_id"  # kv: seria przychodów będąca wypłatą użytkownika (dzień resetu)
CARD_DEBT_KEY = "forecast_card_debt"  # kv: czy odejmować zadłużenie karty (domyślnie tak)
PERIOD_PLAN_KEY = "period_plan"  # kv: limit dzienny z początku okresu (M21 E4)
PAST, NOW, NEXT = "past", "now", "next"  # stan tygodnia okresu
PIGGY_LABEL = "Do skarbonek"


@dataclass
class Balances:
    account: Decimal  # rachunek PLN: dostępne (ITAV), a bez niego zaksięgowane (ITBD)
    card_debt: Decimal  # karta: ITBD = bieżące zadłużenie; bez karty 0
    eur: Decimal | None
    fetched_at: str  # najstarsza z migawek użytych do wyniku


@dataclass(frozen=True)
class Event:
    day: date  # dzień w prognozie: termin serii, a spóźnione liczą się dziś
    due: schedule.Due | None  # None = planowany przelew do skarbonek (M10 E1)
    amount: Decimal  # ze znakiem: wydatek ujemny, wpływ dodatni
    covered: bool = False  # wydatek serii pokryty saldem skarbonki — w prognozie 0

    @property
    def label(self) -> str:
        return self.due.series.name if self.due else PIGGY_LABEL

    @property
    def href(self) -> str:
        return f"/recurring/{self.due.series.id}" if self.due else "/piggy"


@dataclass(frozen=True)
class Week:
    """Tydzień pon–nd okresu wypłaty (M21 E4), przycięty do okresu."""

    start: date
    end: date  # włącznie
    state: str  # PAST / NOW / NEXT
    spent: Decimal  # elastyczne; dla NEXT 0
    limit: Decimal | None  # PAST: plan okresu; NOW: wydane + reszta; NEXT: plan

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def left(self) -> Decimal | None:
        return None if self.limit is None else self.limit - self.spent

    @property
    def used(self) -> float:
        if not self.limit or self.limit <= 0:
            return 1.0 if self.spent > 0 else 0.0
        return min(1.0, float(self.spent / self.limit))

    @property
    def over(self) -> bool:
        return self.limit is not None and self.spent > self.limit


@dataclass
class Projection:
    payday: date | None
    payday_series: str | None
    horizon_end: date
    payday_series_id: int | None = None
    payday_manual: bool = False  # termin wypłaty wpisany ręcznie
    outflows: list[schedule.Due] = field(default_factory=list)
    inflows: list[schedule.Due] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)  # wydatki i wpływy chronologicznie
    flex_total: Decimal = ZERO
    days: list[tuple[date, Decimal]] = field(default_factory=list)  # saldo na koniec dnia
    at_payday: Decimal = ZERO
    low: Decimal = ZERO
    low_day: date | None = None
    piggy_out: Decimal = ZERO  # nieprzelane odłożenie do skarbonek w tym okresie (M10 E1)

    @property
    def series_out(self) -> Decimal:
        return sum((d.series.expected_amount for d in self.outflows), ZERO)

    @property
    def inflows_total(self) -> Decimal:
        return sum((d.series.expected_amount for d in self.inflows), ZERO)


@dataclass
class Forecast(Projection):
    balances: Balances | None = None
    free_now: Decimal = ZERO
    flex_per_day: Decimal = ZERO
    stale: bool = False
    buffer: Decimal = ZERO
    card_debt_included: bool = True
    safe_per_day: Decimal | None = (
        None  # dzienny limit Flex, przy którym dno = bufor; None bez dni Flex
    )
    days_left: int = 0  # dni od dziś do końca horyzontu
    period_start: date | None = None  # dzień ostatniej wypłaty (M21 E3); None bez wypłaty w księdze
    spent_since: Decimal = ZERO  # wydane elastyczne od `period_start` do dziś
    weeks: list[Week] = field(default_factory=list)  # tygodnie okresu (M21 E4)
    plan_per_day: Decimal | None = None  # limit dzienny z początku okresu — miara minionych tygodni
    piggies: list[piggy.Status] = field(default_factory=list)  # stan skarbonek (M10 E1)
    piggies_from: date | None = None  # początek okresu, od którego liczy się „odłożone”

    @property
    def this_week(self) -> Week | None:
        return next((w for w in self.weeks if w.state == NOW), None)

    @property
    def period_elapsed(self) -> float:
        """Część okresu od ostatniej wypłaty do następnej, która minęła (z dzisiejszym dniem)."""
        if self.period_start is None or self.payday is None:
            return 0.0
        total = (self.payday - self.period_start).days
        return min(1.0, (total - self.days_left) / total) if total > 0 else 1.0

    @property
    def below_buffer(self) -> bool:
        return self.low < self.buffer

    @property
    def shortfall(self) -> Decimal:
        return max(self.buffer - self.low, ZERO)


def payday_series_id(conn: sqlite3.Connection) -> int | None:
    value = db.kv_get(conn, PAYDAY_KEY)
    return value if isinstance(value, int) else None


def include_card_debt(conn: sqlite3.Connection) -> bool:
    return db.kv_get(conn, CARD_DEBT_KEY) is not False


def read_balances(conn: sqlite3.Connection) -> Balances | None:
    """Salda z ostatnich migawek; None, gdy rachunek PLN nie ma żadnej."""
    accounts = {
        kind: conn.execute(
            "SELECT id FROM account WHERE kind = ? AND currency = ? ORDER BY id", (kind, cur)
        ).fetchone()
        for kind, cur in (("current", "PLN"), ("card", "PLN"), ("fx", "EUR"))
    }
    snaps = ledger.latest_balances(conn, accounts["current"]["id"]) if accounts["current"] else {}
    main = snaps.get("ITAV") or snaps.get("ITBD")
    if main is None:
        return None
    fetched = [main["fetched_at"]]
    card_debt = ZERO
    if accounts["card"]:
        debt = ledger.latest_balances(conn, accounts["card"]["id"]).get("ITBD")
        if debt is not None:
            card_debt = max(Decimal(debt["amount"]), ZERO)
            fetched.append(debt["fetched_at"])
    eur = None
    if accounts["fx"]:
        row = ledger.latest_balances(conn, accounts["fx"]["id"])
        found = row.get("ITAV") or row.get("ITBD")
        eur = Decimal(found["amount"]) if found else None
    return Balances(Decimal(main["amount"]), card_debt, eur, min(fetched))


def flex_per_day(f: flex.FlexMonth) -> Decimal:
    """Ile dziennie wydaje się z puli od jutra: reszta puli po równo na pozostałe dni miesiąca,
    a gdy pula wyczerpana (albo jej nie ma, albo to ostatni dzień) — dotychczasowe tempo."""
    assert f.day is not None
    after = f.days_in_month - f.day
    if f.remaining is not None and f.remaining > 0 and after > 0:
        return (f.remaining / after).quantize(money.CENT)
    return (f.spent / f.day).quantize(money.CENT) if f.spent > 0 else ZERO


def safe_per_day(
    days: Sequence[tuple[date, Decimal]], today: date, per_day: Decimal, buffer: Decimal = ZERO
) -> Decimal | None:
    """Ile można wydawać dziennie z puli Flex (zamiast `per_day`), żeby saldo nigdy nie spadło
    poniżej bufora: dla każdego dnia `d` po dzisiejszym `per_day + (saldo − bufor) / dni do d`,
    a najostrzejszy dzień rządzi. Ujemny wynik = same serie przekraczają wolne środki;
    None, gdy nie ma dni Flex (horyzont kończy się dziś)."""
    limits = [
        per_day + (balance - buffer) / (day - today).days for day, balance in days if day > today
    ]
    if not limits:
        return None
    return min(limits).quantize(money.CENT, rounding=ROUND_FLOOR)


def _is_payday_candidate(d: schedule.Due, today: date) -> bool:
    """Oczekiwany wpływ po dzisiejszym dniu; spóźniony nie wiadomo, kiedy dotrze."""
    return (
        d.series.direction == "in"
        and d.status == schedule.EXPECTED
        and d.due is not None
        and d.due > today
    )


def project(
    *,
    free_now: Decimal,
    today: date,
    dues: Sequence[schedule.Due],
    per_day: Decimal,
    payday_id: int | None = None,
    piggy_out: Decimal = ZERO,
    covered: frozenset[int] = frozenset(),
) -> Projection:
    """Saldo dzień po dniu od dziś do dnia wypłaty (czysta logika). Wypłata to termin serii
    `payday_id`, a gdy jej nie ma — seria wpływowa o największej kwocie. `piggy_out` schodzi
    dziś (przelew do skarbonek), a wydatki serii z `covered` płaci skarbonka (w prognozie 0)."""
    live = [
        (max(d.due, today), d)
        for d in dues
        if d.due is not None and d.status in (schedule.EXPECTED, schedule.LATE)
    ]
    paydays = [(day, d) for day, d in live if _is_payday_candidate(d, today)]
    own = [p for p in paydays if p[1].series.id == payday_id]
    first = min(
        own or paydays,
        key=lambda p: (-p[1].series.expected_amount, p[0], p[1].series.name),
        default=None,
    )
    end = first[0] if first else card.last_day(today)
    result = Projection(
        first[0] if first else None,
        first[1].series.name if first else None,
        end,
        first[1].series.id if first else None,
        first[1].manual if first else False,
    )
    out = sorted(
        ((day, d) for day, d in live if d.series.direction == "out" and day <= end),
        key=lambda p: p[0],
    )
    inflows = sorted((p for p in paydays if p[0] <= end and p is not first), key=lambda p: p[0])
    result.outflows = [d for _, d in out if d.series.id not in covered]
    result.inflows = [d for _, d in inflows]
    result.piggy_out = piggy_out
    result.events = sorted(
        [
            Event(day, d, ZERO, True)
            if d.series.id in covered
            else Event(day, d, -d.series.expected_amount)
            for day, d in out
        ]
        + [Event(day, d, d.series.expected_amount) for day, d in inflows]
        + ([Event(today, None, -piggy_out)] if piggy_out > 0 else []),
        key=lambda e: (e.day, e.amount > 0, e.label),
    )
    delta: defaultdict[date, Decimal] = defaultdict(Decimal)
    for e in result.events:
        delta[e.day] += e.amount
    balance, day = free_now, today
    while day <= end:
        if day > today:
            balance -= per_day
            result.flex_total += per_day
        balance += delta[day]
        result.days.append((day, balance.quantize(money.CENT)))
        day += timedelta(days=1)
    result.at_payday = result.days[-1][1]
    result.low_day, result.low = min(result.days, key=lambda p: (p[1], p[0]))
    return result


def _dues(
    snap: Snapshot, today: date, mv: schedule.MonthView, payday_id: int | None
) -> list[schedule.Due]:
    """Terminy bieżącego miesiąca (już policzone dla Podsumowania) i, dopóki nie ma wypłaty,
    kolejnych miesięcy."""
    rows, month = list(mv.rows), mv.month
    for _ in range(EXTRA_MONTHS):
        if any(_is_payday_candidate(d, today) and payday_id in (None, d.series.id) for d in rows):
            break
        month = add_months(month, 1)
        rows += schedule.for_month(snap, month, today).rows
    return rows


def for_today(
    snap: Snapshot, today: date, now: datetime, buffer: Decimal = ZERO
) -> Forecast | None:
    """Prognoza z ustawieniami zapisanymi w `kv` (wypłata, zadłużenie karty) — dla dzwonka i encji;
    Podsumowanie woła `build` z już policzonymi `f` i `mv`."""
    first = month_start(today)
    return build(
        snap,
        today,
        now,
        flex.build(snap, first, today),
        schedule.for_month(snap, first, today),
        buffer,
        payday_series_id(snap.conn),
        include_card_debt(snap.conn),
    )


class ForecastMemo:
    """Ostatnia prognoza z sygnaturą bazy, dnia i bufora — dzwonek liczy się na każdej stronie,
    a prognoza (flex + terminy serii) zmienia się dopiero po zapisie w bazie."""

    def __init__(self) -> None:
        self._key: tuple[object, ...] | None = None
        self._value: Forecast | None = None

    def get(self, snap: Snapshot, today: date, now: datetime, buffer: Decimal) -> Forecast | None:
        key = (snap.signature(), today, buffer)
        if key != self._key or snap.conn.in_transaction:
            self._value = for_today(snap, today, now, buffer)
            if not snap.conn.in_transaction:
                self._key = key
        return self._value


def build(
    snap: Snapshot,
    today: date,
    now: datetime,
    f: flex.FlexMonth,
    mv: schedule.MonthView,
    buffer: Decimal = ZERO,
    payday_id: int | None = None,
    card_debt_included: bool = True,
) -> Forecast | None:
    """Prognoza z bazy dla bieżącego miesiąca (`f`, `mv` — już policzone przez Podsumowanie);
    None, gdy rachunek PLN nie ma jeszcze żadnej migawki salda."""
    balances = read_balances(snap.conn)
    if balances is None:
        return None
    if not any(d.series.id == payday_id and d.series.direction == "in" for d in mv.rows):
        payday_id = None  # seria zakończona, usunięta albo nie przychodowa
    free_now = balances.account - (balances.card_debt if card_debt_included else ZERO)
    per_day = flex_per_day(f)
    start = last_payday(snap, payday_id, today)
    piggies_from = start or month_start(today)
    piggies = piggy.statuses(snap, today, piggies_from)
    p = project(
        free_now=free_now,
        today=today,
        dues=_dues(snap, today, mv, payday_id),
        per_day=per_day,
        payday_id=payday_id,
        piggy_out=piggy.total_to_transfer(piggies),
        covered=frozenset(
            s.piggy.series_id
            for s in piggies
            if s.piggy.series_id is not None and s.target and s.balance >= s.target
        ),
    )
    if p.payday_series_id != payday_id:
        start = last_payday(snap, p.payday_series_id, today)
    safe = safe_per_day(p.days, today, per_day, buffer)
    week_list: list[Week] = []
    plan: Decimal | None = None
    spent_since = ZERO
    if start is not None:
        skip = flex.pool_series(snap).skip  # raz na prognozę, nie na każdy tydzień
        if p.payday is not None:
            plan = period_plan(snap.conn, start, safe)
            week_list = weeks(
                start,
                p.payday,
                today,
                lambda a, b: flex.spent_between(snap, a, b, skip),
                plan,
                safe,
            )
            # minione i bieżący tydzień pokrywają dokładnie [start, jutro)
            spent_since = sum((w.spent for w in week_list), ZERO)
        else:
            spent_since = flex.spent_between(snap, start, today + timedelta(days=1), skip)
    return Forecast(
        **vars(p),
        balances=balances,
        free_now=free_now,
        flex_per_day=per_day,
        stale=now - datetime.fromisoformat(balances.fetched_at) > STALE_AFTER,
        buffer=buffer,
        card_debt_included=card_debt_included,
        safe_per_day=safe,
        days_left=(p.horizon_end - today).days,
        period_start=start,
        spent_since=spent_since,
        weeks=week_list,
        plan_per_day=plan,
        piggies=piggies,
        piggies_from=piggies_from,
    )


def period_plan(conn: sqlite3.Connection, start: date, safe: Decimal | None) -> Decimal | None:
    """Limit dzienny zapamiętany przy pierwszej prognozie okresu zaczętego `start` — miara dla
    minionych tygodni; nowy okres nadpisuje wpis. Bez wpisu (np. w transakcji) — `safe`."""
    stored = db.kv_get(conn, PERIOD_PLAN_KEY)
    if isinstance(stored, dict) and stored.get("start") == start.isoformat():
        return Decimal(stored["per_day"])
    if safe is not None and not conn.in_transaction:
        db.kv_set(conn, PERIOD_PLAN_KEY, {"start": start.isoformat(), "per_day": str(safe)})
    return safe


def weeks(
    start: date,
    payday: date,
    today: date,
    spent: Callable[[date, date], Decimal],
    plan: Decimal | None,
    safe: Decimal | None,
) -> list[Week]:
    """Tygodnie pon–nd okresu [start, payday) (czysta logika; `spent(a, b)` = wydane w [a, b)).
    Minione mierzy limit z początku okresu (`plan`), a bieżący i przyszłe — dzisiejszy `safe`
    od jutra (dzisiejsze wydatki są już w saldzie), więc przekroczenie obniża kolejne tygodnie."""
    plan_day = None if plan is None else max(plan, ZERO)
    safe_day = None if safe is None else max(safe, ZERO)
    result: list[Week] = []
    ws = start
    while ws < payday:
        we = min(ws + timedelta(days=6 - ws.weekday()), payday - timedelta(days=1))
        days = (we - ws).days + 1
        if we < today:
            limit = None if plan_day is None else plan_day * days
            result.append(Week(ws, we, PAST, spent(ws, we + timedelta(days=1)), limit))
        elif ws <= today:
            done = spent(ws, today + timedelta(days=1))
            limit = None if safe_day is None else done + safe_day * (we - today).days
            result.append(Week(ws, we, NOW, done, limit))
        else:
            result.append(Week(ws, we, NEXT, ZERO, None if safe_day is None else safe_day * days))
        ws = we + timedelta(days=1)
    return result


def last_payday(snap: Snapshot, series_id: int | None, today: date) -> date | None:
    """Dzień ostatniego wpływu serii wypłaty do dziś — początek bieżącego okresu."""
    if series_id is None:
        return None
    days = [t.day for t in snap.members().get(series_id, []) if t.day <= today]
    return max(days, default=None)
