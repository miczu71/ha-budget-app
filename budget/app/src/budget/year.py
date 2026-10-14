"""Prognoza roczna (M18): saldo miesiąc po miesiącu do końca roku (od listopada do końca
następnego).

Rdzeń `project` jest czystą logiką (jak `forecast.project`): dostaje saldo startowe, terminy
serii pogrupowane po miesiącach i kwoty miesięczne, nic nie czyta z bazy. Bieżący miesiąc liczy
się od dziś — tylko serie, które jeszcze zejdą/wpłyną, i część Flex proporcjonalna do dni.
"""

from __future__ import annotations

import calendar
import sqlite3
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_FLOOR, Decimal

from budget import flex, forecast, money
from budget.categorize import taxonomy
from budget.recurring import schedule
from budget.snapshot import Snapshot
from budget.spending import BASE_CURRENCY, _rows, add_months, month_start, sums
from budget.storage import db

ZERO = Decimal(0)
HISTORY_MONTHS = 12  # pełne miesiące historii do mediany Flex i sezonowości
FLEX_KEY = "year_flex"  # kv: ręczny miesięczny Flex (zamiast mediany)
BACKTEST_KEY = "year_backtest"  # kv: ostatni pomiar metody (Status)
TARGET_KEY = "year_target"  # kv: cel salda na koniec horyzontu (domyślnie 0)
SEASONAL_GROUPS = ("non_monthly", "fixed")  # grupy, których wydatki bez serii są „roczne”
PENDING = (schedule.EXPECTED, schedule.LATE)


@dataclass
class YearMonth:
    month: date
    inflow: Decimal
    series_out: Decimal
    flex: Decimal
    irregular: Decimal  # korekta Flex: rzadkie duże wydatki elastyczne, rozłożone po równo
    seasonal: Decimal  # roczne bez serii: kwota z tego samego miesiąca rok wcześniej
    balance: Decimal  # saldo na koniec miesiąca, narastająco
    below_buffer: bool

    @property
    def net(self) -> Decimal:
        return self.inflow - self.series_out - self.flex - self.irregular - self.seasonal


@dataclass
class Projection:
    months: list[YearMonth] = field(default_factory=list)
    buffer: Decimal = ZERO
    target: Decimal = ZERO
    max_flex: Decimal | None = None  # największy miesięczny Flex, przy którym plan się domyka
    start_balance: Decimal = ZERO
    flex_month: Decimal = ZERO  # miesięczny Flex użyty w prognozie
    flex_manual: bool = False
    history_months: int = 0  # ile pełnych miesięcy historii stoi za medianą

    @property
    def end(self) -> Decimal:
        return self.months[-1].balance

    @property
    def first_deficit(self) -> date | None:
        return next((m.month for m in self.months if m.below_buffer), None)

    def balance_points(self, today: date) -> list[tuple[date, Decimal]]:
        """Saldo dziś i na koniec każdego miesiąca — punkty wykresu."""
        return [(today, self.start_balance)] + [
            (m.month.replace(day=calendar.monthrange(m.month.year, m.month.month)[1]), m.balance)
            for m in self.months
        ]


def horizon_end(today: date) -> date:
    """Koniec roku kalendarzowego; od 1.11 koniec roku następnego."""
    return date(today.year + (1 if today.month >= 11 else 0), 12, 31)


def _horizon_months(today: date) -> list[date]:
    months, m, last = [], month_start(today), horizon_end(today)
    while m <= last:
        months.append(m)
        m = add_months(m, 1)
    return months


def month_fraction(month: date, today: date) -> Decimal:
    """Część miesiąca do policzenia: bieżący — dni po dzisiejszym, kolejne — całość."""
    if month > month_start(today):
        return Decimal(1)
    days = calendar.monthrange(month.year, month.month)[1]
    return Decimal(days - today.day) / Decimal(days)


def _series_sums(dues: Sequence[schedule.Due]) -> tuple[Decimal, Decimal]:
    """Wpływy i wydatki serii, które jeszcze nie weszły do salda; spóźniony wpływ nie wiadomo,
    kiedy dotrze (jak w M8), spóźniony wydatek schodzi."""
    inflow = out = ZERO
    for d in dues:
        if d.due is None or d.status not in PENDING:
            continue
        if d.series.direction == "out":
            out += d.series.expected_amount
        elif d.status == schedule.EXPECTED:
            inflow += d.series.expected_amount
    return inflow, out


def project(
    *,
    start_balance: Decimal,
    today: date,
    dues: Mapping[date, Sequence[schedule.Due]],
    flex: Decimal,
    irregular: Decimal,
    seasonal: Mapping[date, Decimal],
    buffer: Decimal,
    target: Decimal,
) -> Projection:
    """Saldo na koniec każdego miesiąca od bieżącego do końca horyzontu. `max_flex` = największy
    miesięczny Flex, przy którym saldo żadnego miesiąca nie spada poniżej bufora, a na końcu
    wynosi co najmniej `target` (ujemny, gdy same serie łamią bufor)."""
    result = Projection(buffer=buffer, target=target)
    balance = start_balance
    weights = ZERO
    limits: list[Decimal] = []
    base = start_balance
    for month in _horizon_months(today):
        w = month_fraction(month, today)
        inflow, out = _series_sums(dues.get(month, ()))
        rare = (irregular * w).quantize(money.CENT)
        season = (seasonal.get(month, ZERO) * w).quantize(money.CENT)
        spend = (flex * w).quantize(money.CENT)
        balance += inflow - out - spend - rare - season
        result.months.append(
            YearMonth(month, inflow, out, spend, rare, season, balance, balance < buffer)
        )
        base += inflow - out - rare - season
        weights += w
        if w > 0:
            limits.append((base - buffer) / weights)
    if weights > 0:
        limits.append((base - max(target, buffer)) / weights)
        result.max_flex = min(limits).quantize(money.CENT, rounding=ROUND_FLOOR)
    return result


@dataclass
class History:
    flex: Decimal = ZERO  # mediana miesięcznych wydatków elastycznych
    irregular: Decimal = ZERO  # (suma − n × mediana) / n: rzadkie duże wydatki po równo
    months: int = 0
    seasonal: dict[date, Decimal] = field(default_factory=dict)  # roczne bez serii wg miesięcy


def _lookback(month: date, today: date) -> date:
    """Ten sam miesiąc kalendarzowy w ostatnim pełnym roku (nie bieżący i nie przyszły)."""
    cur = month_start(today)
    while month >= cur:
        month = add_months(month, -12)
    return month


def _seasonal_spent(
    snap: Snapshot, month: date, skip_all: set[int], leaves: list[taxonomy.Category]
) -> Decimal:
    """Wydatki grup `SEASONAL_GROUPS` w miesiącu, bez transakcji serii i skarbonek."""
    s = sums(snap.conn, month, add_months(month, 1), skip_all)
    return sum((flex.group_spent(s, leaves, g) for g in SEASONAL_GROUPS), ZERO)


def _skip_all(snap: Snapshot) -> set[int]:
    return {t.id for txns in snap.members().values() for t in txns} | snap.piggy_ids()


def history(
    snap: Snapshot,
    today: date,
    skip: set[int] | None = None,
    skip_all: set[int] | None = None,
) -> History:
    """Mediana Flex i korekta z `HISTORY_MONTHS` pełnych miesięcy oraz sezonowe wydatki roczne
    bez serii (grupy `SEASONAL_GROUPS`, transakcje serii i skarbonek pomijane). `skip`/`skip_all`
    można podać, gdy wołający już je policzył."""
    first = flex.first_month(snap.conn)
    cur = month_start(today)
    if first is None:
        return History()
    skip = flex.pool_series(snap).skip if skip is None else skip
    skip_all = _skip_all(snap) if skip_all is None else skip_all
    spent = [
        flex.spent_between(snap, m, add_months(m, 1), skip)
        for m in (add_months(cur, -n) for n in range(HISTORY_MONTHS, 0, -1))
        if m >= first
    ]
    out = History(months=len(spent))
    if spent:
        median = Decimal(statistics.median(spent))
        out.flex = median.quantize(money.CENT)
        out.irregular = ((sum(spent, ZERO) - len(spent) * median) / len(spent)).quantize(money.CENT)
    leaves = list(taxonomy.leaves(snap.conn).values())
    cache: dict[date, Decimal] = {}
    for m in _horizon_months(today):
        src = _lookback(m, today)
        if src < first:
            continue
        if src not in cache:
            cache[src] = _seasonal_spent(snap, src, skip_all, leaves)
        out.seasonal[m] = cache[src]
    return out


def settings(conn: sqlite3.Connection) -> tuple[Decimal | None, Decimal]:
    """Ręczny Flex (None = mediana) i cel salda na koniec horyzontu z `kv`."""
    manual, target = db.kv_get(conn, FLEX_KEY), db.kv_get(conn, TARGET_KEY)
    return (
        Decimal(manual) if manual is not None else None,
        Decimal(target) if target is not None else ZERO,
    )


def build(snap: Snapshot, today: date, buffer: Decimal = ZERO) -> Projection | None:
    """Prognoza roczna z bazy; None, gdy rachunek PLN nie ma jeszcze migawki salda."""
    balances = forecast.read_balances(snap.conn)
    if balances is None:
        return None
    manual, target = settings(snap.conn)
    past = history(snap, today)
    start = balances.account - (
        balances.card_debt if forecast.include_card_debt(snap.conn) else ZERO
    )
    dues = {m: schedule.for_month(snap, m, today).rows for m in _horizon_months(today)}
    result = project(
        start_balance=start,
        today=today,
        dues=dues,
        flex=past.flex if manual is None else manual,
        irregular=past.irregular if manual is None else ZERO,
        seasonal=past.seasonal,
        buffer=buffer,
        target=target,
    )
    result.start_balance = start
    result.flex_month = past.flex if manual is None else manual
    result.flex_manual = manual is not None
    result.history_months = past.months
    return result


def backtest(snap: Snapshot, today: date, at: str) -> dict[str, object]:
    """Pomiar metody na własnej księdze: prognoza wydatków spoza serii (Flex + korekta +
    sezonowość) z 31 grudnia poprzedniego roku wobec faktu w pełnych miesiącach tego roku.
    Serie pomijamy — ich obecne kwoty znają późniejsze zmiany (np. próg podatkowy), więc pomiar
    nie byłby uczciwy; mierzymy tylko to, co robi M18 sam."""
    skip, skip_all = flex.pool_series(snap).skip, _skip_all(snap)
    leaves = list(taxonomy.leaves(snap.conn).values())
    h = history(snap, date(today.year - 1, 12, 31), skip, skip_all)
    rows: list[tuple[date, Decimal, Decimal]] = []
    month = date(today.year, 1, 1)
    while month < month_start(today):
        predicted = h.flex + h.irregular + h.seasonal.get(month, ZERO)
        actual = flex.spent_between(snap, month, add_months(month, 1), skip) + _seasonal_spent(
            snap, month, skip_all, leaves
        )
        rows.append((month, predicted.quantize(money.CENT), actual.quantize(money.CENT)))
        month = add_months(month, 1)
    predicted = sum((p for _, p, _ in rows), ZERO)
    actual = sum((a for _, _, a in rows), ZERO)
    error = round(float((predicted - actual) / actual * 100), 1) if actual else None
    return {
        "at": at,
        "months": [
            {"month": f"{m:%Y-%m}", "predicted": str(p), "actual": str(a)} for m, p, a in rows
        ],
        "predicted": str(predicted),
        "actual": str(actual),
        "error_pct": error,
        "within_10": error is not None and abs(error) <= 10,
        "history_months": h.months,
    }


def evaluate(snap: Snapshot, today: date, at: str) -> dict[str, object]:
    """Pomiar zapisany w `kv` (`BACKTEST_KEY`), jak `categorize.learn.evaluate`."""
    out = backtest(snap, today, at)
    db.kv_set(snap.conn, BACKTEST_KEY, out)
    return out


@dataclass(frozen=True)
class Unseried:
    name: str
    day: date  # ostatnia płatność
    amount: Decimal  # ostatnia płatność
    count: int  # ile płatności w ostatnich 13 miesiącach


def unseried(snap: Snapshot, today: date, limit: int = 15) -> list[Unseried]:
    """Wydatki z grup `SEASONAL_GROUPS` z ostatnich 13 miesięcy, które nie należą do żadnej serii
    — kandydaci na opłaty roczne/kwartalne do potwierdzenia. Pokrywa je wiersz „roczne bez serii”,
    dopóki użytkownik nie zamieni ich w serię (detektor rzadko łapie roczne: ~21 mies. historii)."""
    allowed = {i for i, c in taxonomy.leaves(snap.conn).items() if c.flex_group in SEASONAL_GROUPS}
    skip = _skip_all(snap)
    start = add_months(month_start(today), -13)
    found: dict[str, list[tuple[date, Decimal]]] = {}
    for r in _rows(snap.conn, start, None, details=True):
        amount = Decimal(r["amount"])
        if (
            amount >= 0
            or r["currency"] != BASE_CURRENCY
            or r["category_id"] not in allowed
            or r["id"] in skip
        ):
            continue
        name = (r["merchant"] or r["counterparty_name"] or r["description"] or "?")[:40]
        found.setdefault(name, []).append((date.fromisoformat(r["day"][:10]), -amount))
    out = []
    for name, items in found.items():
        day, amount = max(items)
        out.append(Unseried(name, day, amount, len(items)))
    out.sort(key=lambda u: (-u.amount, u.name))
    return out[:limit]


class YearError(ValueError):
    pass


def _optional_amount(text: str) -> str | None:
    """Kwota z formularza; puste i zero (wartość domyślna celu) znaczą „brak wpisu”."""
    if not text.strip() or text.strip() in ("0", "0,00", "0.00"):
        return None
    try:
        return str(flex.parse_amount(text))
    except flex.FlexError as exc:
        raise YearError(str(exc)) from exc


def save_settings(conn: sqlite3.Connection, flex_text: str, target_text: str) -> None:
    """Ręczny Flex i cel salda z formularza; puste pole wraca do automatu (Flex) albo do 0 (cel)."""
    flex_value, target_value = _optional_amount(flex_text), _optional_amount(target_text)
    db.kv_set(conn, FLEX_KEY, flex_value)
    db.kv_set(conn, TARGET_KEY, target_value)


class Memo:
    """Ostatnia prognoza z sygnaturą bazy, dnia i bufora; jedna instancja w `Service`."""

    def __init__(self) -> None:
        self._key: tuple[object, ...] | None = None
        self._value: Projection | None = None

    def get(self, snap: Snapshot, today: date, buffer: Decimal) -> Projection | None:
        key = (snap.signature(), today, buffer)
        if key != self._key or snap.conn.in_transaction:
            self._value = build(snap, today, buffer)
            if not snap.conn.in_transaction:
                self._key = key
        return self._value
