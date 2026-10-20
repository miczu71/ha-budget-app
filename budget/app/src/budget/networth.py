"""Majątek netto (M26 E1, decyzja 31) — tylko majątek finansowy, w PLN.

Aktywa: konta z migawek sald (EUR po kursie średnim NBP), oszczędności M10 (z odsetkami),
skarbonki, aktywa z Inwestycji (M22) bez tych powiązanych z kontem M10. Pasywa: kredyty M9
(kapitał wg harmonogramu) i zadłużenie karty (ITBD). Płynność = (konta + oszczędności +
skarbonki) / miesięczne wydatki; LTV = kredyty / aktywa.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from budget import fx, invest, ledger, loan, money, piggy, savings
from budget.snapshot import Snapshot
from budget.spending import month_start

ZERO = money.ZERO
STALE_DAYS = 90  # wartość aktywa z Inwestycji starsza niż tyle dni = „zaktualizuj”

ACCOUNTS, SAVINGS, PIGGIES, INVESTMENTS, LOANS, CARD = (
    "konta",
    "oszczędności",
    "skarbonki",
    "inwestycje",
    "kredyty",
    "karta",
)
LIQUID_GROUPS = (ACCOUNTS, SAVINGS, PIGGIES)
NO_RATE = "brak kursu NBP"


@dataclass(frozen=True)
class Component:
    group: str
    name: str
    amount: Decimal  # PLN, zawsze dodatnia; strona wynika z `liability`
    liability: bool = False
    note: str | None = None  # np. „120 EUR po 4,2500”, „brak kursu”
    stale: bool = False  # wartość wpisana ręcznie jest przeterminowana


@dataclass(frozen=True)
class NetWorth:
    day: date
    components: tuple[Component, ...]
    spend: Decimal | None = None  # miesięczne wydatki do płynności (z prognozy), jeśli znane

    @property
    def assets(self) -> Decimal:
        return sum((c.amount for c in self.components if not c.liability), ZERO)

    @property
    def liabilities(self) -> Decimal:
        return sum((c.amount for c in self.components if c.liability), ZERO)

    @property
    def total(self) -> Decimal:
        return self.assets - self.liabilities

    @property
    def liquid(self) -> Decimal:
        return sum((c.amount for c in self.components if c.group in LIQUID_GROUPS), ZERO)

    @property
    def liquidity_months(self) -> Decimal | None:
        """Płynne aktywa w miesiącach wydatków; None bez znanych wydatków."""
        if not self.spend or self.spend <= 0:
            return None
        return (self.liquid / self.spend).quantize(Decimal("0.1"))

    @property
    def ltv(self) -> Decimal | None:
        """Kredyty do aktywów (0–1+); None bez aktywów albo bez kredytu."""
        loans = sum((c.amount for c in self.components if c.group == LOANS), ZERO)
        if loans <= 0 or self.assets <= 0:
            return None
        return (loans / self.assets).quantize(Decimal("0.0001"))

    @property
    def stale(self) -> list[Component]:
        return [c for c in self.components if c.stale]

    @property
    def missing_fx(self) -> bool:
        return any(c.note == NO_RATE for c in self.components)


def _balance(conn: sqlite3.Connection, account_id: int) -> Decimal | None:
    snaps = ledger.latest_balances(conn, account_id)
    found = snaps.get("ITAV") or snaps.get("ITBD")
    return Decimal(found["amount"]) if found else None


def _after(conn: sqlite3.Connection, account_id: int, day: date) -> Decimal:
    """Suma zaksięgowanych transakcji konta po `day` (do cofania salda z migawki)."""
    rows = conn.execute(
        "SELECT amount FROM txn WHERE account_id = ? AND status = 'BOOK' "
        "AND coalesce(booking_date, tx_date) > ?",
        (account_id, day.isoformat()),
    )
    return sum((Decimal(r[0]) for r in rows), ZERO)


def _card_started(conn: sqlite3.Connection, account_id: int, day: date) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM txn WHERE account_id = ? AND status = 'BOOK' "
            "AND coalesce(booking_date, tx_date) <= ? LIMIT 1",
            (account_id, day.isoformat()),
        ).fetchone()
        is not None
    )


def _accounts(conn: sqlite3.Connection, day: date, past: bool) -> list[Component]:
    rates = fx.Rates(conn)
    out: list[Component] = []
    rows = conn.execute("SELECT * FROM account ORDER BY id").fetchall()
    for r in rows:
        name = r["display_name"] or r["product"] or f"Konto {r['id']}"
        if r["kind"] == "card":
            debt = ledger.latest_balances(conn, r["id"]).get("ITBD")
            amount = max(Decimal(debt["amount"]), ZERO) if debt else ZERO
            if past:  # dług = dzisiejszy + wydatki po dniu (kwoty ujemne); przed kartą 0
                started = _card_started(conn, r["id"], day)
                amount = max(amount + _after(conn, r["id"], day), ZERO) if started else ZERO
            if amount > 0:
                out.append(Component(CARD, name, amount, liability=True))
            continue
        bal = _balance(conn, r["id"])
        if bal is None:
            continue
        if past:
            bal -= _after(conn, r["id"], day)
        if r["currency"] == "PLN":
            out.append(Component(ACCOUNTS, name, bal))
            continue
        rate = rates.at(r["currency"], day)
        if rate is None:
            out.append(Component(ACCOUNTS, name, ZERO, note=NO_RATE))
            continue
        pln = (bal * rate[1]).quantize(money.CENT)
        out.append(Component(ACCOUNTS, name, pln, note=f"{bal} {r['currency']} po {rate[1]:.4f}"))
    return out


def _savings(conn: sqlite3.Connection, day: date) -> list[Component]:
    return [
        Component(SAVINGS, a.name, savings.estimate(conn, a, day).total)
        for a in savings.all_accounts(conn)
        if a.opening_date <= day
    ]


def _piggies_at(conn: sqlite3.Connection, day: date) -> list[Component]:
    """Saldo skarbonki na `day`: stan otwarcia + wpłaty netto do tego dnia (jak `statuses`)."""
    piggies = piggy.all_piggies(conn)
    paid: dict[str, Decimal] = {}
    for r in piggy.transfers(conn, [p.account_number for p in piggies]):
        if r["day"] <= day.isoformat():
            paid[r["number"]] = paid.get(r["number"], ZERO) - Decimal(r["amount"])
    return [
        Component(PIGGIES, p.name, p.opening_balance + paid.get(p.account_number, ZERO))
        for p in piggies
    ]


def _piggies(conn: sqlite3.Connection, day: date) -> list[Component]:
    return [
        Component(PIGGIES, s.piggy.name, s.balance)
        for s in piggy.statuses(Snapshot(conn), day, month_start(day))
    ]


def _investments(conn: sqlite3.Connection, day: date, past: bool = False) -> list[Component]:
    out = []
    for a in invest.all_assets(conn):
        if a.savings_id is not None:
            continue  # liczone raz, jako oszczędność M10
        if past and a.start is not None and a.start > day:
            continue  # dzisiejsza wartość od startu, wcześniej 0
        stale = a.valued_at is None or a.valued_at < day - timedelta(days=STALE_DAYS)
        note = f"wartość z {a.valued_at:%d.%m.%Y}" if a.valued_at else None
        out.append(Component(INVESTMENTS, a.name, a.amount, note=note, stale=stale))
    return out


def _loans(conn: sqlite3.Connection, day: date) -> list[Component]:
    return [
        Component(LOANS, lo.name, loan.summary(lo, loan.schedule(lo), day).principal, True)
        for lo in loan.all_loans(conn)
        if lo.principal_date <= day
    ]


def compute(
    conn: sqlite3.Connection, day: date, spend: Decimal | None = None, past: bool = False
) -> NetWorth:
    """Majątek netto na `day` z bieżących danych (salda z ostatnich migawek, kurs NBP z `fx_rate`).
    `spend` = miesięczne wydatki do wskaźnika płynności (z prognozy); bez niego płynność jest
    nieznana. `past`: dzień z przeszłości — salda kont cofnięte o późniejsze transakcje,
    skarbonki z przelewów do tego dnia, aktywa Inwestycji dopiero od startu."""
    parts = (
        _accounts(conn, day, past),
        _savings(conn, day),
        _piggies_at(conn, day) if past else _piggies(conn, day),
        _investments(conn, day, past),
        _loans(conn, day),
    )
    return NetWorth(day, tuple(c for part in parts for c in part), spend)


def reconstruct(conn: sqlite3.Connection, day: date) -> NetWorth:
    """Przybliżony majątek na dzień z przeszłości (bez płynności — brak wydatków z tamtego dnia)."""
    return compute(conn, day, past=True)


def save(conn: sqlite3.Connection, nw: NetWorth, approx: bool = False) -> None:
    """Zapis migawki dnia. Dokładna (`approx=False`) zastępuje wpis; przybliżona nigdy nie
    nadpisuje istniejącego."""
    comps = [
        {
            "group": c.group,
            "name": c.name,
            "amount": str(c.amount),
            "liability": c.liability,
            "note": c.note,
            "stale": c.stale,
        }
        for c in nw.components
    ]
    verb = "INSERT OR IGNORE" if approx else "INSERT OR REPLACE"
    conn.execute(
        f"{verb} INTO networth_snapshot (day, total, assets, liabilities, components_json, approx) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            nw.day.isoformat(),
            str(nw.total),
            str(nw.assets),
            str(nw.liabilities),
            json.dumps(comps, ensure_ascii=False),
            int(approx),
        ),
    )


def has_history(conn: sqlite3.Connection, before: date) -> bool:
    """Są migawki sprzed `before` (dzisiejsza nie blokuje ponowienia odtwarzania)."""
    return (
        conn.execute(
            "SELECT 1 FROM networth_snapshot WHERE day < ? LIMIT 1", (before.isoformat(),)
        ).fetchone()
        is not None
    )


def first_day(conn: sqlite3.Connection) -> date | None:
    """Dzień najstarszej zaksięgowanej transakcji — początek odtwarzanej historii."""
    row = conn.execute(
        "SELECT min(coalesce(booking_date, tx_date)) FROM txn WHERE status = 'BOOK'"
    ).fetchone()
    return date.fromisoformat(row[0]) if row and row[0] else None


def backfill(conn: sqlite3.Connection, today: date) -> int:
    """Jednorazowe odtworzenie końców miesięcy od najstarszej transakcji do ostatniego przed
    `today` (`approx=1`). Nic nie robi, gdy migawki już są; zwraca liczbę zapisanych."""
    first = first_day(conn)
    if first is None or has_history(conn, today):
        return 0
    n, day = 0, month_start(first)
    while True:
        end = (day + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        if end >= today:
            return n
        save(conn, reconstruct(conn, end), approx=True)
        n, day = n + 1, end + timedelta(days=1)


@dataclass(frozen=True)
class Point:
    day: date
    total: Decimal
    approx: bool


def history(conn: sqlite3.Connection) -> list[Point]:
    """Ostatnia migawka każdego miesiąca (bieżący miesiąc kończy dzisiejsza), od najstarszej."""
    rows = conn.execute(
        "SELECT day, total, approx FROM networth_snapshot s WHERE day = "
        "(SELECT max(day) FROM networth_snapshot WHERE substr(day, 1, 7) = substr(s.day, 1, 7)) "
        "ORDER BY day"
    )
    return [Point(date.fromisoformat(r[0]), Decimal(r[1]), bool(r[2])) for r in rows]


@dataclass(frozen=True)
class Change:
    delta: Decimal
    since: date
    approx: bool  # punkt odniesienia odtworzony, nie zapisany na bieżąco


def change(conn: sqlite3.Connection, now: Decimal, today: date, days: int) -> Change | None:
    """Zmiana wobec ostatniej migawki z dnia `today − days` lub wcześniejszej; None bez niej."""
    row = conn.execute(
        "SELECT day, total, approx FROM networth_snapshot WHERE day <= ? ORDER BY day DESC LIMIT 1",
        ((today - timedelta(days=days)).isoformat(),),
    ).fetchone()
    if row is None:
        return None
    return Change(now - Decimal(row[1]), date.fromisoformat(row[0]), bool(row[2]))
