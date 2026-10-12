"""Konto oszczędnościowe poza Enable Banking (M10 E2, decyzja 26).

Saldo = saldo wpisane na dzień + przelewy z rachunków w księdze na numer konta (wpłata) i z niego
(wypłata) po tej dacie. Przelewy na konto nie liczą się do puli Flex (`snapshot.piggy_ids`).
Numer konta tylko w bazie, w panelu maskowany. Odsetki i promocja — E3, stopa oszczędności — E4.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from budget import money, piggy
from budget.categorize import taxonomy
from budget.logging_utils import mask_iban
from budget.piggy import PiggyError
from budget.spending import add_months, month_start, sums, totals
from budget.storage.db import now_iso

ZERO = money.ZERO
BELKA = Decimal("0.19")  # podatek od odsetek, potrącany przy kapitalizacji
PROMO_REMIND_DAYS = (14, 3)  # przypomnienie o końcu promocji tyle dni przed (push)
PROMO_BELL_DAYS = 14  # karta w dzwonku od tylu dni przed końcem promocji


class SavingsError(PiggyError):
    pass


@dataclass(frozen=True)
class Account:
    id: int
    name: str
    account_number: str
    opening_balance: Decimal
    opening_date: date
    base_rate: Decimal | None = None  # % rocznie
    promo_rate: Decimal | None = None
    promo_limit: Decimal | None = None  # promocja obejmuje saldo do tej kwoty (None = całe)
    promo_until: date | None = None

    @property
    def masked(self) -> str:
        return mask_iban("PL" + self.account_number)


def _row(r: sqlite3.Row) -> Account:
    return Account(
        id=r["id"],
        name=r["name"],
        account_number=r["account_number"],
        opening_balance=Decimal(r["opening_balance"]),
        opening_date=date.fromisoformat(r["opening_date"]),
        base_rate=Decimal(r["base_rate"]) if r["base_rate"] else None,
        promo_rate=Decimal(r["promo_rate"]) if r["promo_rate"] else None,
        promo_limit=Decimal(r["promo_limit"]) if r["promo_limit"] else None,
        promo_until=date.fromisoformat(r["promo_until"]) if r["promo_until"] else None,
    )


def all_accounts(conn: sqlite3.Connection) -> list[Account]:
    return [
        _row(r)
        for r in conn.execute(
            "SELECT * FROM savings_account WHERE archived_at IS NULL ORDER BY name"
        )
    ]


def get(conn: sqlite3.Connection, account_id: int) -> Account:
    row = conn.execute("SELECT * FROM savings_account WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise SavingsError("Nie ma takiego konta oszczędnościowego.")
    return _row(row)


def _rate(value: str | None, what: str) -> Decimal | None:
    """Stopa roczna w procentach (0–100) albo None, gdy puste."""
    if value is None or not value.strip():
        return None
    try:
        rate = money.parse(value)
    except money.AmountError:
        rate = None
    if rate is None or rate < ZERO or rate > 100:
        raise SavingsError(f"Podaj {what} w procentach, np. 5 albo 4,5.")
    return rate


def save(
    conn: sqlite3.Connection,
    *,
    account_id: int | None,
    name: str,
    account_number: str,
    opening_balance: str | None,
    opening_date: str | None,
    base_rate: str | None = None,
    promo_rate: str | None = None,
    promo_limit: str | None = None,
    promo_until: str | None = None,
) -> int:
    """Nowe konto (`account_id` None) albo zmiana (pusty numer = bez zmiany — panel pokazuje go
    zamaskowany). Nowe saldo na nowy dzień to korekta względem banku."""
    clean = " ".join(name.split())[:40]
    if not clean:
        raise SavingsError("Podaj nazwę konta.")
    if account_id is not None and not account_number.strip():
        number = get(conn, account_id).account_number
    else:
        number = piggy.normalize_number(account_number)
    try:
        day = date.fromisoformat(opening_date or "")
    except ValueError as exc:
        raise SavingsError("Podaj datę salda.") from exc
    opening = piggy._amount(opening_balance, "saldo konta", allow_zero=True) or ZERO
    base, promo = _rate(base_rate, "stopę bazową"), _rate(promo_rate, "stopę promocyjną")
    limit = piggy._amount(promo_limit, "limit promocji")
    until = None
    if promo_until:
        try:
            until = date.fromisoformat(promo_until)
        except ValueError as exc:
            raise SavingsError("Podaj datę końca promocji.") from exc
    if promo is not None and until is None:
        raise SavingsError("Do stopy promocyjnej podaj datę końca promocji.")
    rates = (base, promo, limit, until.isoformat() if until else None)
    params = (
        clean,
        number,
        str(opening),
        day.isoformat(),
        *(None if v is None else str(v) for v in rates),
    )
    try:
        if account_id is None:
            cur = conn.execute(
                "INSERT INTO savings_account (name, account_number, opening_balance, "
                "opening_date, base_rate, promo_rate, promo_limit, promo_until, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*params, now_iso()),
            )
            return int(cur.lastrowid or 0)
        cur = conn.execute(
            "UPDATE savings_account SET name = ?, account_number = ?, opening_balance = ?, "
            "opening_date = ?, base_rate = ?, promo_rate = ?, promo_limit = ?, promo_until = ? "
            "WHERE id = ?",
            (*params, account_id),
        )
    except sqlite3.IntegrityError as exc:
        raise SavingsError("Konto o tej nazwie albo tym numerze już jest.") from exc
    if not cur.rowcount:
        raise SavingsError("Nie ma takiego konta oszczędnościowego.")
    return account_id


def archive(conn: sqlite3.Connection, account_id: int) -> None:
    cur = conn.execute(
        "UPDATE savings_account SET archived_at = ? WHERE id = ?", (now_iso(), account_id)
    )
    if not cur.rowcount:
        raise SavingsError("Nie ma takiego konta oszczędnościowego.")


def movements(conn: sqlite3.Connection, acc: Account) -> list[sqlite3.Row]:
    """Przelewy po dacie salda: `id`, `day`, `amount` ze znakiem rachunku (ujemny = wpłata)."""
    return [
        r
        for r in piggy.transfers(conn, [acc.account_number])
        if date.fromisoformat(r["day"]) > acc.opening_date
    ]


def balance(conn: sqlite3.Connection, acc: Account) -> Decimal:
    return acc.opening_balance - sum((Decimal(r["amount"]) for r in movements(conn, acc)), ZERO)


def txn_ids(conn: sqlite3.Connection) -> set[int]:
    """Przelewy na konta oszczędnościowe i z nich (poza pulą Flex — cała historia, nie tylko
    po dacie salda)."""
    numbers = [r[0] for r in conn.execute("SELECT account_number FROM savings_account")]
    return {r["id"] for r in piggy.transfers(conn, numbers)}


@dataclass(frozen=True)
class Interest:
    balance: Decimal  # saldo z odsetkami skapitalizowanymi na koniec zamkniętych miesięcy
    earned: Decimal  # odsetki netto (po Belce) skapitalizowane od daty salda
    accrued: Decimal  # odsetki netto naliczone w bieżącym miesiącu, jeszcze nieskapitalizowane

    @property
    def total(self) -> Decimal:
        return self.balance + self.accrued

    @property
    def interest(self) -> Decimal:
        return self.earned + self.accrued


def _daily(acc: Account, bal: Decimal, day: date) -> Decimal:
    """Brutto odsetki za dzień: saldo do limitu po stopie promocyjnej (do daty końca), reszta po
    bazowej; rok = 365 dni."""
    bal = max(bal, ZERO)
    promo_part = ZERO
    if acc.promo_rate is not None and acc.promo_until and day <= acc.promo_until:
        promo_part = min(bal, acc.promo_limit) if acc.promo_limit else bal
    promo = promo_part * (acc.promo_rate or ZERO)
    return (promo + (bal - promo_part) * (acc.base_rate or ZERO)) / 100 / 365


def _net(gross: Decimal) -> Decimal:
    return (gross * (1 - BELKA)).quantize(money.CENT, ROUND_HALF_UP)


def estimate(conn: sqlite3.Connection, acc: Account, today: date) -> Interest:
    """Szacunek odsetek dzień po dniu od daty salda do `today`: kapitalizacja na koniec miesiąca,
    odsetki netto (Belka). Bank liczy co do grosza inaczej — stąd ręczna korekta salda."""
    flows: dict[date, Decimal] = defaultdict(Decimal)
    for r in movements(conn, acc):
        flows[date.fromisoformat(r["day"])] -= Decimal(r["amount"])
    bal, earned, gross = acc.opening_balance, ZERO, ZERO
    day = acc.opening_date
    while day < today:
        day += timedelta(days=1)
        bal += flows.get(day, ZERO)
        gross += _daily(acc, bal, day)
        if (day + timedelta(days=1)).month != day.month:
            capital = _net(gross)
            bal, earned, gross = bal + capital, earned + capital, ZERO
    return Interest(bal, earned, _net(gross))


@dataclass(frozen=True)
class MonthRate:
    month: date
    saved: Decimal  # wpłaty na konta oszczędnościowe minus wypłaty z nich (skarbonki się nie liczą)
    income: Decimal  # wpływy miesiąca wg `spending.totals`

    @property
    def rate(self) -> Decimal | None:
        return self.saved / self.income if self.income > 0 else None

    @property
    def frac(self) -> float:
        """Udział do paska: 0–1 (ujemny albo brak wpływów = pusty pasek)."""
        return max(0.0, min(1.0, float(self.rate or 0)))


def monthly_rates(conn: sqlite3.Connection, today: date, n: int = 12) -> list[MonthRate]:
    """Stopa oszczędności ostatnich `n` miesięcy do bieżącego włącznie, od najstarszego. Wpływy
    bez przelewów z kont oszczędnościowych i skarbonek — wypłata z nich nie jest dochodem."""
    numbers = [r[0] for r in conn.execute("SELECT account_number FROM savings_account")]
    saved: dict[date, Decimal] = defaultdict(Decimal)
    for r in piggy.transfers(conn, numbers):
        saved[month_start(date.fromisoformat(r["day"]))] -= Decimal(r["amount"])
    skip = txn_ids(conn) | piggy.txn_ids(conn)
    leaves, current = taxonomy.leaves(conn), month_start(today)
    out = []
    for back in range(n - 1, -1, -1):
        month = add_months(current, -back)
        income, _ = totals(leaves, sums(conn, month, add_months(month, 1), skip))
        out.append(MonthRate(month, saved[month], income))
    return out


@dataclass(frozen=True)
class Overview:
    total: Decimal  # saldo wszystkich kont z odsetkami
    rates: list[MonthRate]

    @property
    def current(self) -> MonthRate:
        return self.rates[-1]


def overview(conn: sqlite3.Connection, today: date) -> Overview | None:
    accts = all_accounts(conn)
    if not accts:
        return None
    total = sum((estimate(conn, a, today).total for a in accts), ZERO)
    return Overview(total, monthly_rates(conn, today))
