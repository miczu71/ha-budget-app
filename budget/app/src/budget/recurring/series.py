"""Serie płatności cyklicznych: zapis, walidacja i przynależność transakcji.

Seria to warunki jak w regułach kategorii (`categorize.rules.Conditions`) + kadencja i
oczekiwana kwota. Przynależność transakcji do serii nie jest zapisywana — liczy się od zera
z warunków (wzorzec silnika kategorii), więc edycja warunków działa od razu wstecz. Gdy
transakcja pasuje do kilku serii, należy do tej, której oczekiwana kwota jest najbliższa.

Kandydaci do serii to transakcje liczone w budżecie: zaksięgowane, bez przelewów
wewnętrznych, w PLN, z kont „w budżecie”.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from budget import money
from budget.categorize import engine
from budget.categorize.rules import Conditions, Facts, RuleError, _norm
from budget.categorize.rules import parse_amount as rule_amount
from budget.storage.db import now_iso

CADENCES = {"M": "co miesiąc", "Q": "co kwartał", "Y": "co rok"}
CADENCE_DAYS = {"M": 30.44, "Q": 91.31, "Y": 365.25}
STATUSES = {
    "proposed": "propozycja",
    "active": "aktywna",
    "ended": "zakończona",
    "rejected": "odrzucona",
}
MEMBER_STATUSES = ("proposed", "active", "ended")  # odrzucona nie obejmuje transakcji
NAME_MAX = 60
FEW_HISTORY = 3  # seria roczna z mniejszą liczbą wystąpień — „mało historii”

CANDIDATES_WHERE = (
    "t.status = 'BOOK' AND t.transfer_group IS NULL AND t.currency = 'PLN' "
    "AND a.include_in_budget = 1"
)


class SeriesError(ValueError):
    """Komunikat dla użytkownika panelu."""


@dataclass(frozen=True)
class Series:
    id: int
    name: str
    direction: str
    cadence: str
    conditions: Conditions
    expected_amount: Decimal
    tolerance: Decimal
    anchor_day: int | None
    status: str
    origin: str
    group_key: str | None
    created_at: str
    decided_at: str | None

    @property
    def monthly(self) -> Decimal:
        """Oczekiwana kwota w przeliczeniu na miesiąc (Q = ⅓, Y = 1/12)."""
        div = {"M": 1, "Q": 3, "Y": 12}[self.cadence]
        return (self.expected_amount / div).quantize(money.CENT)


@dataclass(frozen=True)
class Candidate:
    id: int
    day: date
    amount: Decimal  # ze znakiem
    merchant: str  # nazwa wyświetlana (z ewentualną zmianą nazwy z reguły)
    description: str
    facts: Facts
    category_id: int | None = None

    @property
    def direction(self) -> str:
        return "in" if self.amount > 0 else "out"


def _row(r: sqlite3.Row) -> Series:
    return Series(
        id=int(r["id"]),
        name=r["name"],
        direction=r["direction"],
        cadence=r["cadence"],
        conditions=Conditions.from_json(r["matcher_json"]),
        expected_amount=Decimal(r["expected_amount"]),
        tolerance=Decimal(r["tolerance"]),
        anchor_day=r["anchor_day"],
        status=r["status"],
        origin=r["origin"],
        group_key=r["group_key"],
        created_at=r["created_at"],
        decided_at=r["decided_at"],
    )


def all_series(conn: sqlite3.Connection, statuses: Iterable[str] | None = None) -> list[Series]:
    rows = conn.execute("SELECT * FROM series ORDER BY id").fetchall()
    wanted = set(statuses) if statuses is not None else None
    return [_row(r) for r in rows if wanted is None or r["status"] in wanted]


def get(conn: sqlite3.Connection, series_id: int) -> Series:
    row = conn.execute("SELECT * FROM series WHERE id = ?", (series_id,)).fetchone()
    if row is None:
        raise SeriesError("Nie ma takiej serii.")
    return _row(row)


def count_proposed(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT count(*) FROM series WHERE status = 'proposed'").fetchone()[0])


def group_key(merchant: str, direction: str) -> str:
    return f"{_norm('merchant', merchant)}|{direction}"


def candidates(conn: sqlite3.Connection, ids: Sequence[int] | None = None) -> list[Candidate]:
    """Transakcje, które mogą należeć do serii, rosnąco po dacie (`ids` — tylko te z listy)."""
    only = ""
    if ids is not None:
        only = f"AND t.id IN ({','.join('?' * len(ids))}) "
    rows = conn.execute(
        "SELECT t.id, coalesce(t.tx_date, t.booking_date) AS day, t.amount, t.merchant, "
        "t.description, t.category_id FROM txn t JOIN account a ON a.id = t.account_id "
        f"WHERE {CANDIDATES_WHERE} "
        f"AND coalesce(t.tx_date, t.booking_date) IS NOT NULL {only}ORDER BY day, t.id",
        list(ids) if ids is not None else [],
    ).fetchall()
    known = engine.facts(conn, [int(r["id"]) for r in rows])
    out = []
    for r in rows:
        f = known[int(r["id"])]
        out.append(
            Candidate(
                id=int(r["id"]),
                day=date.fromisoformat(str(r["day"])[:10]),
                amount=Decimal(r["amount"]),
                merchant=r["merchant"] or f.merchant,
                description=r["description"] or "",
                facts=f,
                category_id=r["category_id"],
            )
        )
    return out


def _merchant_equals(cond: Conditions) -> str | None:
    for c in cond.text:
        if c.field == "merchant" and c.op == "equals":
            return _norm("merchant", c.value)
    return None


def assign(series: Sequence[Series], txns: Sequence[Candidate]) -> dict[int, list[Candidate]]:
    """Transakcje każdej serii (id serii → lista rosnąco po dacie); odrzucone pomijane.

    Seria z warunkiem „sprzedawca równa się X” sprawdza tylko transakcje sprzedawcy X."""
    live = [s for s in series if s.status in MEMBER_STATUSES]
    by_merchant: dict[str, list[Series]] = defaultdict(list)
    general: list[Series] = []
    for s in live:
        if (key := _merchant_equals(s.conditions)) is not None:
            by_merchant[key].append(s)
        else:
            general.append(s)
    out: dict[int, list[Candidate]] = {s.id: [] for s in live}
    for t in txns:
        pool = by_merchant.get(_norm("merchant", t.facts.merchant), []) + general
        if not pool:
            continue
        hits = [s for s in pool if s.direction == t.direction and s.conditions.matches(t.facts)]
        if hits:
            best = min(hits, key=lambda s: (abs(abs(t.amount) - s.expected_amount), s.id))
            out[best.id].append(t)
    return out


def covered_ids(members: dict[int, list[Candidate]]) -> set[int]:
    return {t.id for txns in members.values() for t in txns}


def few_history(s: Series, members: Sequence[Candidate]) -> bool:
    return s.cadence == "Y" and len(members) < FEW_HISTORY


# --- zapis ------------------------------------------------------------------------------------


def validate(
    name: str,
    cadence: str,
    conditions: Conditions,
    expected: Decimal | None,
    tolerance: Decimal | None,
) -> tuple[str, Decimal, Decimal]:
    """Sprawdzone pola serii (nazwa, kwota, tolerancja) albo `SeriesError`."""
    name = " ".join(name.split())
    if not name:
        raise SeriesError("Podaj nazwę serii.")
    if len(name) > NAME_MAX:
        raise SeriesError(f"Nazwa serii może mieć najwyżej {NAME_MAX} znaków.")
    if cadence not in CADENCES:
        raise SeriesError("Wybierz kadencję.")
    if not conditions.text and conditions.kind is None:
        raise SeriesError("Seria potrzebuje warunku tekstowego albo typu transakcji.")
    if conditions.direction not in ("out", "in"):
        raise SeriesError("Wybierz kierunek: wydatek albo wpływ.")
    if expected is None or expected <= 0:
        raise SeriesError("Podaj oczekiwaną kwotę większą od zera.")
    if tolerance is None:
        tolerance = Decimal(0)
    return name, expected.quantize(money.CENT), tolerance.quantize(money.CENT)


def parse_amount(value: str | None) -> Decimal | None:
    try:
        return rule_amount(value)
    except RuleError as exc:
        raise SeriesError(str(exc)) from exc


def insert(
    conn: sqlite3.Connection,
    *,
    name: str,
    direction: str,
    cadence: str,
    conditions: Conditions,
    expected: Decimal,
    tolerance: Decimal,
    anchor_day: int | None,
    status: str,
    origin: str,
    key: str | None,
) -> int:
    now = now_iso()
    cur = conn.execute(
        "INSERT INTO series (name, direction, cadence, matcher_json, expected_amount, tolerance, "
        "anchor_day, status, origin, group_key, created_at, decided_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            name,
            direction,
            cadence,
            conditions.to_json(),
            money.fmt(expected),
            money.fmt(tolerance),
            anchor_day,
            status,
            origin,
            key,
            now,
            None if status == "proposed" else now,
        ),
    )
    return int(cur.lastrowid or 0)


def save(
    conn: sqlite3.Connection,
    series_id: int,
    *,
    name: str,
    cadence: str,
    conditions: Conditions,
    expected: Decimal | None,
    tolerance: Decimal | None,
    activate: bool = False,
) -> Series:
    """Edycja serii; `activate` — potwierdzenie propozycji (status → aktywna)."""
    current = get(conn, series_id)
    if current.status == "rejected":
        raise SeriesError("Odrzucona propozycja nie może być edytowana.")
    name, amount, tol = validate(name, cadence, conditions, expected, tolerance)
    status = "active" if activate else current.status
    decided = now_iso() if activate else current.decided_at
    conn.execute(
        "UPDATE series SET name = ?, direction = ?, cadence = ?, matcher_json = ?, "
        "expected_amount = ?, tolerance = ?, status = ?, decided_at = ? WHERE id = ?",
        (
            name,
            conditions.direction,
            cadence,
            conditions.to_json(),
            money.fmt(amount),
            money.fmt(tol),
            status,
            decided,
            series_id,
        ),
    )
    return get(conn, series_id)


TRANSITIONS = {
    "confirm": ({"proposed"}, "active"),
    "reject": ({"proposed"}, "rejected"),
    "end": ({"active"}, "ended"),
    "restore": ({"ended"}, "active"),
}


def set_status(conn: sqlite3.Connection, series_id: int, action: str) -> Series:
    current = get(conn, series_id)
    allowed, target = TRANSITIONS[action]
    if current.status not in allowed:
        raise SeriesError(f"Seria „{current.name}” jest {STATUSES[current.status]}.")
    conn.execute(
        "UPDATE series SET status = ?, decided_at = ? WHERE id = ?",
        (target, now_iso(), series_id),
    )
    return get(conn, series_id)
