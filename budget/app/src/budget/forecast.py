"""Prognoza „czy starczy do wypłaty” (M8 E1): wolne środki dzień po dniu do najbliższej wypłaty.

Wolne środki dziś = saldo rachunku PLN (dostępne, już bez autoryzacji) − bieżące zadłużenie karty.
Przyszłość: oczekiwane i spóźnione wydatki serii w ich terminach (spóźnione liczą się dziś),
reszta puli Flex po równo na dni, wpływy serii przed wypłatą. Wydatki zrobione dziś są już
w saldzie i zadłużeniu karty, więc Flex liczy się od jutra. Spóźniony wpływ nie jest
wypłatą ani nie zwiększa salda — nie wiadomo, kiedy dotrze. Wypłata = najbliższy termin aktywnej
serii wpływowej o największej oczekiwanej kwocie (mniejsze wpływy przed nią wchodzą do salda);
bez takiej serii horyzont kończy się z miesiącem. Saldo na dzień wypłaty jest przed jej
wpłynięciem, bo tam leży dno. Termin wypłaty w miesiącu można przestawić ręcznie (M21 E1,
`schedule.set_override`).
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal

from budget import card, flex, ledger, money
from budget.recurring import schedule
from budget.snapshot import Snapshot
from budget.spending import add_months, month_start
from budget.storage import db

ZERO = Decimal(0)
EXTRA_MONTHS = 2  # ile następnych miesięcy sprawdzamy, gdy bieżący nie ma już wypłaty
STALE_AFTER = timedelta(hours=24)
PAYDAY_KEY = "payday_series_id"  # kv: seria przychodów będąca wypłatą użytkownika (dzień resetu)
CARD_DEBT_KEY = "forecast_card_debt"  # kv: czy odejmować zadłużenie karty (domyślnie tak)


@dataclass
class Balances:
    account: Decimal  # rachunek PLN: dostępne (ITAV), a bez niego zaksięgowane (ITBD)
    card_debt: Decimal  # karta: ITBD = bieżące zadłużenie; bez karty 0
    eur: Decimal | None
    fetched_at: str  # najstarsza z migawek użytych do wyniku


@dataclass(frozen=True)
class Event:
    day: date  # dzień w prognozie: termin serii, a spóźnione liczą się dziś
    due: schedule.Due
    amount: Decimal  # ze znakiem: wydatek ujemny, wpływ dodatni


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
) -> Projection:
    """Saldo dzień po dniu od dziś do dnia wypłaty (czysta logika). Wypłata to termin serii
    `payday_id`, a gdy jej nie ma — seria wpływowa o największej kwocie."""
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
    inflows = sorted((p for p in paydays if p[0] < end), key=lambda p: p[0])
    result.outflows, result.inflows = [d for _, d in out], [d for _, d in inflows]
    result.events = sorted(
        [Event(day, d, -d.series.expected_amount) for day, d in out]
        + [Event(day, d, d.series.expected_amount) for day, d in inflows],
        key=lambda e: (e.day, e.amount > 0, e.due.series.name),
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
    p = project(
        free_now=free_now,
        today=today,
        dues=_dues(snap, today, mv, payday_id),
        per_day=per_day,
        payday_id=payday_id,
    )
    start = last_payday(snap, p.payday_series_id, today)
    return Forecast(
        **vars(p),
        balances=balances,
        free_now=free_now,
        flex_per_day=per_day,
        stale=now - datetime.fromisoformat(balances.fetched_at) > STALE_AFTER,
        buffer=buffer,
        card_debt_included=card_debt_included,
        safe_per_day=safe_per_day(p.days, today, per_day, buffer),
        days_left=(p.horizon_end - today).days,
        period_start=start,
        spent_since=flex.spent_between(snap, start, today + timedelta(days=1)) if start else ZERO,
    )


def last_payday(snap: Snapshot, series_id: int | None, today: date) -> date | None:
    """Dzień ostatniego wpływu serii wypłaty do dziś — początek bieżącego okresu."""
    if series_id is None:
        return None
    days = [t.day for t in snap.members().get(series_id, []) if t.day <= today]
    return max(days, default=None)
