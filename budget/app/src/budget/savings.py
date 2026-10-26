"""Konto oszczędnościowe poza Enable Banking (M10 E2, decyzja 26).

Saldo = saldo wpisane na dzień + przelewy z rachunków w księdze na numer konta (wpłata) i z niego
(wypłata) po tej dacie. Przelewy na konto nie liczą się do puli Flex (`snapshot.piggy_ids`).
Numer konta tylko w bazie, w panelu maskowany. Odsetki i promocja — E3, stopa oszczędności — E4.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from budget import ledger, money, piggy
from budget.logging_utils import mask_iban
from budget.piggy import PiggyError
from budget.spending import month_start, monthly_totals
from budget.storage.db import now_iso

ZERO = money.ZERO
BELKA = Decimal("0.19")  # podatek od odsetek, potrącany przy kapitalizacji
PROMO_FUNDS_MAX = Decimal(200_000)  # limit nowych środków w promocji Profit
PROMO_DAYS = 91  # okres promocyjny Profit liczony od dnia przystąpienia (ed. 77)
PARK_DAYS = 7  # wypłata z konta nadrzędnego i wpłata na parking w tylu dniach = przeniesienie
PARK_TOLERANCE = Decimal(1)  # dopuszczalna różnica kwot (zł) przy parowaniu przeniesienia
PROMO_REMIND_DAYS = (14, 3)  # push o końcu promocji tyle dni przed; dzwonek od pierwszego z nich


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
    parking_for: int | None = None  # id konta, z którego pochodzą zaparkowane tu środki

    @property
    def masked(self) -> str:
        return mask_iban("PL" + self.account_number)

    def promo_days_left(self, today: date) -> int | None:
        """Dni do końca promocyjnej stopy (0 = dziś); None bez promocji albo po jej końcu."""
        if self.promo_rate is None or self.promo_until is None or self.promo_until < today:
            return None
        return (self.promo_until - today).days


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
        parking_for=r["parking_for"],
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


def _date(value: str | None, message: str) -> date:
    try:
        return date.fromisoformat(value or "")
    except ValueError as exc:
        raise SavingsError(message) from exc


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
    parking_for: int | None = None,
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
    day = _date(opening_date, "Podaj datę salda.")
    opening = piggy.parse_amount(opening_balance, "saldo konta", allow_zero=True) or ZERO
    base, promo = _rate(base_rate, "stopę bazową"), _rate(promo_rate, "stopę promocyjną")
    limit = piggy.parse_amount(promo_limit, "limit promocji")
    until = _date(promo_until, "Podaj datę końca promocji.") if promo_until else None
    if promo is not None and until is None:
        raise SavingsError("Do stopy promocyjnej podaj datę końca promocji.")
    _check_parking(conn, account_id, parking_for)
    rates = (base, promo, limit, until.isoformat() if until else None)
    params = (
        clean,
        number,
        str(opening),
        day.isoformat(),
        *(None if v is None else str(v) for v in rates),
        parking_for,
    )
    try:
        if account_id is None:
            cur = conn.execute(
                "INSERT INTO savings_account (name, account_number, opening_balance, "
                "opening_date, base_rate, promo_rate, promo_limit, promo_until, parking_for, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*params, now_iso()),
            )
            return int(cur.lastrowid or 0)
        cur = conn.execute(
            "UPDATE savings_account SET name = ?, account_number = ?, opening_balance = ?, "
            "opening_date = ?, base_rate = ?, promo_rate = ?, promo_limit = ?, promo_until = ?, "
            "parking_for = ? WHERE id = ?",
            (*params, account_id),
        )
    except sqlite3.IntegrityError as exc:
        raise SavingsError("Konto o tej nazwie albo tym numerze już jest.") from exc
    if not cur.rowcount:
        raise SavingsError("Nie ma takiego konta oszczędnościowego.")
    return account_id


def _check_parking(conn: sqlite3.Connection, account_id: int | None, parent: int | None) -> None:
    if parent is None:
        return
    if parent == account_id:
        raise SavingsError("Konto nie może być parkingiem dla siebie.")
    if get(conn, parent).parking_for is not None:
        raise SavingsError("To konto samo jest parkingiem — wybierz konto nadrzędne.")


def activate_promo(
    conn: sqlite3.Connection,
    account_id: int,
    *,
    base_rate: str | None,
    promo_rate: str | None,
    new_funds: str | None,
    start: str | None,
    days: int = PROMO_DAYS,
) -> None:
    """Promocja „Nowe środki” (Profit): stawka łączna do kwoty nowych środków (do 200 tys.) przez
    `days` dni od dnia przystąpienia (ostatni dzień = start + days − 1), potem stawka bazowa."""
    acc = get(conn, account_id)
    day = _date(start, "Podaj datę przystąpienia do promocji.")
    funds = piggy.parse_amount(new_funds, "kwotę nowych środków")
    if funds is None or funds > PROMO_FUNDS_MAX:
        raise SavingsError(
            f"Nowe środki: podaj kwotę do {PROMO_FUNDS_MAX:,.0f} zł.".replace(",", " ")
        )
    if not (promo_rate or "").strip():
        raise SavingsError("Podaj łączną stawkę promocyjną, np. 5,25.")
    save(
        conn,
        account_id=acc.id,
        name=acc.name,
        account_number="",
        opening_balance=str(acc.opening_balance),
        opening_date=acc.opening_date.isoformat(),
        base_rate=base_rate,
        promo_rate=promo_rate,
        promo_limit=str(funds),
        promo_until=(day + timedelta(days=days - 1)).isoformat(),
    )


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


def _numbers(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT account_number FROM savings_account")]


def txn_ids(conn: sqlite3.Connection) -> set[int]:
    """Przelewy na konta oszczędnościowe i z nich (poza pulą Flex — cała historia, nie tylko
    po dacie salda)."""
    return {r["id"] for r in piggy.transfers(conn, _numbers(conn))}


def parked(conn: sqlite3.Connection, today: date) -> list[tuple[str, Decimal]]:
    """Konta-parkingi z dodatnim saldem (nazwa, saldo z odsetkami) — środki do zwrotu na konto
    nadrzędne przy nowej edycji promocji."""
    out = [(a.name, estimate(conn, a, today).total) for a in all_accounts(conn) if a.parking_for]
    return [(name, bal) for name, bal in out if bal > 0]


@dataclass(frozen=True)
class Interest:
    balance: Decimal  # saldo z odsetkami skapitalizowanymi na koniec zamkniętych miesięcy
    earned: Decimal  # odsetki netto (po Belce) skapitalizowane od daty salda
    accrued: Decimal  # odsetki netto naliczone w bieżącym miesiącu, jeszcze nieskapitalizowane
    pending: Decimal = ZERO  # konto z banku: odsetki „do dopisania”, NIE wchodzą do `total`
    as_of: date | None = None  # konto z banku: data salda z API (None = saldo ręczne)

    @property
    def total(self) -> Decimal:
        return self.balance + self.accrued

    @property
    def interest(self) -> Decimal:
        return self.earned + self.accrued


def daily(acc: Account, bal: Decimal, day: date) -> Decimal:
    """Brutto odsetki za dzień: saldo do limitu po stopie promocyjnej (do daty końca), reszta po
    bazowej; rok = 365 dni."""
    bal = max(bal, ZERO)
    promo_part = ZERO
    if acc.promo_rate is not None and acc.promo_until and day <= acc.promo_until:
        promo_part = min(bal, acc.promo_limit) if acc.promo_limit else bal
    promo = promo_part * (acc.promo_rate or ZERO)
    return (promo + (bal - promo_part) * (acc.base_rate or ZERO)) / 100 / 365


def net(gross: Decimal) -> Decimal:
    return (gross * (1 - BELKA)).quantize(money.CENT, ROUND_HALF_UP)


def linked_ledger_id(conn: sqlite3.Connection, acc: Account) -> int | None:
    """Konto z księgi o tym samym numerze (NRB = IBAN bez `PL`); None bez powiązania."""
    for r in conn.execute("SELECT id, iban FROM account WHERE iban IS NOT NULL ORDER BY id"):
        if r["iban"].replace(" ", "").upper().removeprefix("PL") == acc.account_number:
            return int(r["id"])
    return None


def bank_snapshot(conn: sqlite3.Connection, acc: Account) -> sqlite3.Row | None:
    """Ostatnia migawka salda (ITAV, potem ITBD) powiązanego konta z księgi; None bez niej."""
    ledger_id = linked_ledger_id(conn, acc)
    if ledger_id is None:
        return None
    snaps = ledger.latest_balances(conn, ledger_id)
    return snaps.get("ITAV") or snaps.get("ITBD")


def _from_bank(acc: Account, snap: sqlite3.Row, today: date) -> Interest:
    """Saldo z API; odsetki od ostatniej kapitalizacji (1. dnia miesiąca) tylko jako `pending`."""
    bal = Decimal(snap["amount"])
    day, gross = month_start(today), ZERO
    while day <= today:
        gross += daily(acc, bal, day)
        day += timedelta(days=1)
    return Interest(
        bal, ZERO, ZERO, pending=net(gross), as_of=date.fromisoformat(snap["fetched_at"][:10])
    )


def estimate(
    conn: sqlite3.Connection, acc: Account, today: date, *, use_bank: bool = True
) -> Interest:
    """Szacunek odsetek dzień po dniu od daty salda do `today`: kapitalizacja na koniec miesiąca,
    odsetki netto (Belka). Bank liczy co do grosza inaczej — stąd ręczna korekta salda.
    Konto powiązane z księgą (migawka salda) bierze saldo z banku, bez szacunku od `opening_*`;
    `use_bank=False` (historia Majątku: migawka jest dzisiejsza) wymusza szacunek ręczny."""
    snap = bank_snapshot(conn, acc) if use_bank else None
    if snap is not None:
        return _from_bank(acc, snap, today)
    flows: dict[date, Decimal] = defaultdict(Decimal)
    for r in movements(conn, acc):
        flows[date.fromisoformat(r["day"])] -= Decimal(r["amount"])
    bal, earned, gross = acc.opening_balance, ZERO, ZERO
    day = acc.opening_date
    while day < today:
        day += timedelta(days=1)
        bal += flows.get(day, ZERO)
        gross += daily(acc, bal, day)
        if (day + timedelta(days=1)).month != day.month:
            capital = net(gross)
            bal, earned, gross = bal + capital, earned + capital, ZERO
    return Interest(bal, earned, net(gross))


@dataclass(frozen=True)
class Move:
    day: date
    amount: Decimal  # + wpłata na konto oszczędnościowe, − wypłata z niego
    account: str
    transfer: bool = (
        False  # przeniesienie między kontami oszczędnościowymi (poza stopą oszczędności)
    )


def _paired(rows: list[tuple[int, Move]]) -> set[int]:
    """Indeksy `rows` (konto, ruch) sparowane jako przeniesienie między dwoma RÓŻNYMI kontami
    oszczędnościowymi: przeciwne kwoty, do `PARK_DAYS` dni od siebie i z kwotą różną o najwyżej
    `PARK_TOLERANCE`. Ruchy iterowane wg daty; dla każdego niesparowanego szukany jest najbliższy
    niesparowany ruch z innego konta. Każdy ruch w jednej parze."""
    paired: set[int] = set()
    by_day = sorted(range(len(rows)), key=lambda k: rows[k][1].day)
    for i in by_day:
        if i in paired:
            continue
        a = rows[i][1]
        cands = [
            j
            for j in by_day
            if j not in paired
            and rows[j][0] != rows[i][0]
            and abs((a.day - rows[j][1].day).days) <= PARK_DAYS
            and a.amount * rows[j][1].amount < 0
            and abs(a.amount + rows[j][1].amount) <= PARK_TOLERANCE
        ]
        if cands:
            j = min(cands, key=lambda k: abs((a.day - rows[k][1].day).days))
            paired |= {i, j}
    return paired


@dataclass(frozen=True)
class MonthRate:
    month: date
    income: Decimal  # wpływy miesiąca wg `spending.totals`
    moves: tuple[Move, ...] = ()

    @property
    def saved(self) -> Decimal:
        """Wpłaty na konta oszczędnościowe minus wypłaty z nich (skarbonki i przeniesienia między
        kontami oszczędnościowymi się nie liczą)."""
        return sum((m.amount for m in self.moves if not m.transfer), ZERO)

    @property
    def by_account(self) -> list[tuple[str, Decimal, list[Move]]]:
        """Przelewy miesiąca per konto (nazwa, netto, przelewy po dacie), konta alfabetycznie."""
        grouped: dict[str, list[Move]] = defaultdict(list)
        for mv in sorted(self.moves, key=lambda m: m.day):
            grouped[mv.account].append(mv)
        return [
            (name, sum((m.amount for m in rows), ZERO), rows)
            for name, rows in sorted(grouped.items())
        ]

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
    accts = conn.execute("SELECT id, account_number, name, parking_for FROM savings_account")
    info = {r["account_number"]: r for r in accts.fetchall()}
    transfers = piggy.transfers(conn, list(info))
    rows = [
        (
            info[r["number"]]["id"],
            Move(
                date.fromisoformat(r["day"]),
                -Decimal(r["amount"]),
                info[r["number"]]["name"],
            ),
        )
        for r in transfers
    ]
    paired = _paired(rows)
    moves: dict[date, list[Move]] = defaultdict(list)
    for idx, (_, mv) in enumerate(rows):
        flagged = replace(mv, transfer=True) if idx in paired else mv
        moves[month_start(mv.day)].append(flagged)
    skip = {r["id"] for r in transfers} | piggy.txn_ids(conn)
    return [
        MonthRate(t.month, t.income, tuple(moves[t.month]))
        for t in monthly_totals(conn, today, n, skip)
    ]


@dataclass(frozen=True)
class Overview:
    total: Decimal  # saldo wszystkich kont z odsetkami
    rates: list[MonthRate]

    @property
    def current(self) -> MonthRate:
        return self.rates[-1]


def overview(conn: sqlite3.Connection, today: date, n: int = 12) -> Overview | None:
    """Saldo i stopa oszczędności z ostatnich `n` miesięcy; None bez kont."""
    accts = all_accounts(conn)
    if not accts:
        return None
    total = sum((estimate(conn, a, today).total for a in accts), ZERO)
    return Overview(total, monthly_rates(conn, today, n))
