"""Skarbonki na kontach-celach w banku (M10 E1, decyzja 25).

Enable Banking nie widzi kont-celów, więc saldo skarbonki = saldo początkowe + przelewy z rachunków
w księdze na numer konta-celu (wpłata) i z niego (wypłata). Zalecane odłożenie w bieżącym okresie
wypłaty = (cel − saldo na początek okresu) / miesiące do terminu; cel i termin daje seria cykliczna
(kwota, następna płatność) albo wpis użytkownika. Przelewy na konta-cele i ręcznie przypisane
wydatki nie liczą się do puli Flex (`flex.pool_series`). Numer konta tylko w bazie, w panelu
maskowany.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, Decimal

from budget import money
from budget.logging_utils import mask_iban
from budget.recurring import schedule
from budget.recurring import series as S
from budget.snapshot import Snapshot
from budget.spending import add_months, month_start
from budget.storage.db import now_iso

ZERO = money.ZERO
AMOUNT_MAX = Decimal(10_000_000)
NEXT_DUE_MONTHS = 13  # jak daleko szukamy następnej płatności serii (roczna + zapas)
_MATCH = "substr(replace(upper(t.counterparty_account), ' ', ''), -26)"  # 26 cyfr NRB


class PiggyError(ValueError):
    pass


@dataclass(frozen=True)
class Piggy:
    id: int
    name: str
    account_number: str
    target: Decimal | None
    due_date: date | None
    series_id: int | None
    opening_balance: Decimal

    @property
    def masked(self) -> str:
        return mask_iban("PL" + self.account_number)


@dataclass
class Status:
    piggy: Piggy
    balance: Decimal
    target: Decimal | None
    due: date | None
    monthly: Decimal  # zalecane odłożenie w bieżącym okresie
    saved: Decimal  # odłożone (netto) od początku okresu
    spent: Decimal  # wydatki przypisane do skarbonki (informacyjnie)
    series_name: str | None = None

    @property
    def to_transfer(self) -> Decimal:
        return max(self.monthly - self.saved, ZERO)

    @property
    def progress(self) -> float:
        if not self.target or self.target <= 0:
            return 0.0
        return max(0.0, min(1.0, float(self.balance / self.target)))


def _row(r: sqlite3.Row) -> Piggy:
    return Piggy(
        id=r["id"],
        name=r["name"],
        account_number=r["account_number"],
        target=Decimal(r["target"]) if r["target"] else None,
        due_date=date.fromisoformat(r["due_date"]) if r["due_date"] else None,
        series_id=r["series_id"],
        opening_balance=Decimal(r["opening_balance"]),
    )


def all_piggies(conn: sqlite3.Connection, archived: bool = False) -> list[Piggy]:
    """Aktywne skarbonki, a z `archived` — tylko zarchiwizowane."""
    where = "IS NOT NULL" if archived else "IS NULL"
    return [
        _row(r)
        for r in conn.execute(f"SELECT * FROM piggy WHERE archived_at {where} ORDER BY name")
    ]


def get(conn: sqlite3.Connection, piggy_id: int) -> Piggy:
    row = conn.execute("SELECT * FROM piggy WHERE id = ?", (piggy_id,)).fetchone()
    if row is None:
        raise PiggyError("Nie ma takiej skarbonki.")
    return _row(row)


def normalize_number(value: str) -> str:
    """Numer konta-celu → 26 cyfr (bez spacji, kresek i „PL”)."""
    compact = re.sub(r"[\s-]", "", value.upper())
    compact = compact.removeprefix("PL")
    if not re.fullmatch(r"\d{26}", compact):
        raise PiggyError("Podaj numer konta-celu: 26 cyfr (spacje i „PL” mogą zostać).")
    return compact


def parse_amount(value: str | None, what: str, *, allow_zero: bool = False) -> Decimal | None:
    if value is None or not value.strip():
        return None
    try:
        amount = money.parse(value)
    except money.AmountError:
        amount = None
    low = ZERO if allow_zero else money.CENT
    if amount is None or amount < low or amount >= AMOUNT_MAX:
        raise PiggyError(f"Podaj {what}, np. 1200 albo 1 200,00.")
    return amount


def save(
    conn: sqlite3.Connection,
    *,
    piggy_id: int | None,
    name: str,
    account_number: str,
    target: str | None,
    due_date: str | None,
    series_id: int | None,
    opening_balance: str | None,
) -> int:
    """Nowa skarbonka (`piggy_id` None) albo zmiana (pusty numer = bez zmiany, bo panel pokazuje
    go zamaskowany); bez serii cel i termin są wymagane."""
    clean = " ".join(name.split())[:40]
    if not clean:
        raise PiggyError("Podaj nazwę skarbonki.")
    if piggy_id is not None and not account_number.strip():
        number = get(conn, piggy_id).account_number
    else:
        number = normalize_number(account_number)
    goal = parse_amount(target, "kwotę celu")
    due = None
    if due_date:
        try:
            due = date.fromisoformat(due_date)
        except ValueError as exc:
            raise PiggyError("Podaj termin jako datę.") from exc
    if series_id is not None:
        S.get(conn, series_id)  # SeriesError, gdy nie ma
    elif goal is None or due is None:
        raise PiggyError("Bez serii podaj kwotę celu i termin.")
    opening = parse_amount(opening_balance, "saldo początkowe", allow_zero=True) or ZERO
    values = (clean, number, str(goal) if goal else None, due.isoformat() if due else None)
    params = (*values, series_id, str(opening))
    try:
        if piggy_id is None:
            cur = conn.execute(
                "INSERT INTO piggy (name, account_number, target, due_date, series_id, "
                "opening_balance, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (*params, now_iso()),
            )
            return int(cur.lastrowid or 0)
        cur = conn.execute(
            "UPDATE piggy SET name = ?, account_number = ?, target = ?, due_date = ?, "
            "series_id = ?, opening_balance = ? WHERE id = ?",
            (*params, piggy_id),
        )
    except sqlite3.IntegrityError as exc:
        raise PiggyError("Skarbonka o tej nazwie albo tym numerze konta już jest.") from exc
    if not cur.rowcount:
        raise PiggyError("Nie ma takiej skarbonki.")
    return piggy_id


def archive(conn: sqlite3.Connection, piggy_id: int, archived: bool = True) -> None:
    cur = conn.execute(
        "UPDATE piggy SET archived_at = ? WHERE id = ?",
        (now_iso() if archived else None, piggy_id),
    )
    if not cur.rowcount:
        raise PiggyError("Nie ma takiej skarbonki.")


def assign(conn: sqlite3.Connection, txn_id: int, piggy_id: int | None) -> None:
    """Wydatek ze skarbonki (albo zdjęcie przypisania, `piggy_id` None)."""
    row = conn.execute("SELECT amount FROM txn WHERE id = ?", (txn_id,)).fetchone()
    if row is None or Decimal(row["amount"]) >= 0:
        raise PiggyError("Do skarbonki przypisuje się tylko wydatki.")
    if piggy_id is not None:
        get(conn, piggy_id)
    conn.execute("UPDATE txn SET piggy_id = ? WHERE id = ?", (piggy_id, txn_id))


def transfers(conn: sqlite3.Connection, numbers: list[str]) -> list[sqlite3.Row]:
    """Zaksięgowane przelewy na konta-cele i z nich: `number`, `id`, `day`, `amount` (ze znakiem
    rachunku w księdze — ujemny = wpłata do skarbonki)."""
    if not numbers:
        return []
    marks = ", ".join("?" for _ in numbers)
    return conn.execute(
        f"SELECT t.id, {_MATCH} AS number, coalesce(t.tx_date, t.booking_date) AS day, t.amount "
        f"FROM txn t WHERE t.status = 'BOOK' AND t.counterparty_account IS NOT NULL "
        f"AND {_MATCH} IN ({marks})",
        numbers,
    ).fetchall()


def txn_ids(conn: sqlite3.Connection) -> set[int]:
    """Transakcje poza pulą Flex: przelewy na/z kont-celów i wydatki przypisane do skarbonek."""
    numbers = [r[0] for r in conn.execute("SELECT account_number FROM piggy")]
    if not numbers:
        return set()
    ids = {r["id"] for r in transfers(conn, numbers)}
    ids |= {r[0] for r in conn.execute("SELECT id FROM txn WHERE piggy_id IS NOT NULL")}
    return ids


def next_due(snap: Snapshot, s: S.Series, today: date) -> date | None:
    """Najbliższy termin serii od dziś (włącznie)."""
    members = snap.members().get(s.id, [])
    month = month_start(today)
    for n in range(NEXT_DUE_MONTHS):
        due = schedule.due_date(s, members, add_months(month, n))
        if due is not None and due >= today:
            return due
    return None


def total_to_transfer(rows: list[Status]) -> Decimal:
    """Ile jeszcze przelać na konta-cele w bieżącym okresie (suma po skarbonkach)."""
    return sum((s.to_transfer for s in rows), ZERO)


def months_left(today: date, due: date) -> int:
    """Ile miesięcy odkładania do terminu, z bieżącym (termin w tym miesiącu = 1)."""
    return max((due.year - today.year) * 12 + due.month - today.month, 1)


def statuses(snap: Snapshot, today: date, period_start: date) -> list[Status]:
    """Stan aktywnych skarbonek; `period_start` = początek okresu wypłaty (albo miesiąca)."""
    conn = snap.conn
    piggies = all_piggies(conn)
    if not piggies:
        return []
    cut = period_start.isoformat()
    before_by: defaultdict[str, Decimal] = defaultdict(Decimal)  # wpłaty netto przed okresem
    saved_by: defaultdict[str, Decimal] = defaultdict(Decimal)  # i od początku okresu
    for r in transfers(conn, [p.account_number for p in piggies]):
        (before_by if r["day"] < cut else saved_by)[r["number"]] -= Decimal(r["amount"])
    spent_by: defaultdict[int, Decimal] = defaultdict(Decimal)
    for r in conn.execute(
        "SELECT piggy_id, amount FROM txn WHERE piggy_id IS NOT NULL AND status = 'BOOK'"
    ):
        spent_by[r["piggy_id"]] -= Decimal(r["amount"])
    series_by_id = {s.id: s for s in S.all_series(conn)}
    out = []
    for p in piggies:
        before = p.opening_balance + before_by[p.account_number]
        saved = saved_by[p.account_number]
        s = series_by_id.get(p.series_id) if p.series_id is not None else None
        target, due = (s.expected_amount, next_due(snap, s, today)) if s else (p.target, p.due_date)
        monthly = ZERO
        if target is not None and due is not None and due >= today:
            missing = max(target - before, ZERO)
            # pełne złote (bez reszt typu „przelej 0,02 zł”), ale nigdy więcej niż brakuje
            monthly = min(
                (missing / months_left(today, due)).to_integral_value(ROUND_CEILING), missing
            )
        out.append(
            Status(
                piggy=p,
                balance=before + saved,
                target=target,
                due=due,
                monthly=monthly,
                saved=saved,
                spent=spent_by[p.id],
                series_name=s.name if s else None,
            )
        )
    return out
