"""Majątek netto (M26 E1, decyzja 31) — tylko majątek finansowy, w PLN.

Aktywa: konta z migawek sald (EUR po kursie średnim NBP), oszczędności M10 (z odsetkami),
skarbonki, aktywa z Inwestycji (M22) bez tych powiązanych z kontem M10. Pasywa: kredyty M9
(kapitał wg harmonogramu) i zadłużenie karty (ITBD). Płynność = (konta + oszczędności +
skarbonki) / miesięczne wydatki; LTV = kredyty / aktywa.
"""

from __future__ import annotations

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


def _accounts(conn: sqlite3.Connection, day: date) -> list[Component]:
    rates = fx.Rates(conn)
    out: list[Component] = []
    rows = conn.execute("SELECT * FROM account ORDER BY id").fetchall()
    for r in rows:
        name = r["display_name"] or r["product"] or f"Konto {r['id']}"
        if r["kind"] == "card":
            debt = ledger.latest_balances(conn, r["id"]).get("ITBD")
            amount = max(Decimal(debt["amount"]), ZERO) if debt else ZERO
            if amount > 0:
                out.append(Component(CARD, name, amount, liability=True))
            continue
        bal = _balance(conn, r["id"])
        if bal is None:
            continue
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
    ]


def _piggies(conn: sqlite3.Connection, day: date) -> list[Component]:
    return [
        Component(PIGGIES, s.piggy.name, s.balance)
        for s in piggy.statuses(Snapshot(conn), day, month_start(day))
    ]


def _investments(conn: sqlite3.Connection, day: date) -> list[Component]:
    out = []
    for a in invest.all_assets(conn):
        if a.savings_id is not None:
            continue  # liczone raz, jako oszczędność M10
        stale = a.valued_at is None or a.valued_at < day - timedelta(days=STALE_DAYS)
        note = f"wartość z {a.valued_at:%d.%m.%Y}" if a.valued_at else None
        out.append(Component(INVESTMENTS, a.name, a.amount, note=note, stale=stale))
    return out


def _loans(conn: sqlite3.Connection, day: date) -> list[Component]:
    return [
        Component(LOANS, lo.name, loan.summary(lo, loan.schedule(lo), day).principal, True)
        for lo in loan.all_loans(conn)
    ]


def compute(conn: sqlite3.Connection, day: date, spend: Decimal | None = None) -> NetWorth:
    """Majątek netto na `day` z bieżących danych (salda z ostatnich migawek, kurs NBP z `fx_rate`).
    `spend` = miesięczne wydatki do wskaźnika płynności (z prognozy); bez niego płynność jest
    nieznana."""
    parts = (_accounts, _savings, _piggies, _investments, _loans)
    return NetWorth(day, tuple(c for part in parts for c in part(conn, day)), spend)
