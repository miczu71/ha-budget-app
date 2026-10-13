"""Koszty ukryte (M23 E3): ile kosztuje bank poza ceną zakupów.

Przewalutowanie: koszt = −(kwota PLN − kwota walutowa × kurs NBP) ze znakami transakcji — dla zakupu
to dopłata ponad kurs średni NBP (marża Visy + prowizja banku), dla zwrotu to, ile bank oddał mniej.
Kwota walutowa jest tylko w CSV karty (API jej nie podaje, M23 E0), więc dane sięgają do ostatniego
importu (`csv_until`). Brak kursu = koszt nieznany (liczony w `missing`), nigdy zgadywany.
Opłaty: suma transakcji `Kind.FEE` (zwroty opłat pomniejszają).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from budget import fx
from budget.kinds import Kind
from budget.spending import add_months

CENT = Decimal("0.01")


@dataclass(frozen=True)
class FxItem:
    txn_id: int
    day: date
    description: str
    amount: Decimal  # PLN ze znakiem
    orig: Decimal  # waluta ze znakiem
    currency: str
    nbp: Decimal | None

    @property
    def cost(self) -> Decimal | None:
        if self.nbp is None:
            return None
        return (-(self.amount - self.orig * self.nbp)).quantize(CENT)

    @property
    def pct(self) -> Decimal | None:
        """Koszt w % wartości po kursie NBP (jedno miejsce po przecinku)."""
        cost = self.cost
        if cost is None or not self.orig:
            return None
        return (cost / abs(self.orig * (self.nbp or 0)) * 100).quantize(Decimal("0.1"))


@dataclass(frozen=True)
class Fee:
    txn_id: int
    day: date
    description: str
    amount: Decimal  # ze znakiem: obciążenie ujemne, zwrot opłaty dodatni


@dataclass
class Costs:
    start: date
    fx: list[FxItem] = field(default_factory=list)
    fee_items: list[Fee] = field(default_factory=list)

    @property
    def fees(self) -> Decimal:
        return -sum((f.amount for f in self.fee_items), Decimal("0"))

    @property
    def priced(self) -> list[FxItem]:
        return [i for i in self.fx if i.cost is not None]

    @property
    def fx_cost(self) -> Decimal:
        return sum((i.cost or Decimal("0") for i in self.fx), Decimal("0"))

    @property
    def fx_volume(self) -> Decimal:
        """Wartość transakcji walutowych po kursie NBP (podstawa średniego %)."""
        return sum((abs(i.orig * (i.nbp or 0)) for i in self.priced), Decimal("0")).quantize(CENT)

    @property
    def fx_pct(self) -> Decimal | None:
        if not self.fx_volume:
            return None
        return (self.fx_cost / self.fx_volume * 100).quantize(Decimal("0.1"))

    @property
    def missing(self) -> int:
        return len(self.fx) - len(self.priced)

    @property
    def total(self) -> Decimal:
        return self.fx_cost + self.fees


def build(conn: sqlite3.Connection, start: date, end: date) -> Costs:
    """Koszty transakcji zaksięgowanych w [start, end) według daty transakcji."""
    out = Costs(start)
    span = (start.isoformat(), end.isoformat())
    for r in conn.execute(
        "SELECT id, COALESCE(tx_date, booking_date) AS day, description, amount, orig_amount, "
        "orig_currency FROM txn WHERE status = 'BOOK' AND orig_currency IS NOT NULL "
        "AND orig_currency <> currency AND orig_amount IS NOT NULL "
        "AND COALESCE(tx_date, booking_date) >= ? AND COALESCE(tx_date, booking_date) < ? "
        "ORDER BY day DESC, id DESC",
        span,
    ):
        day = date.fromisoformat(r["day"])
        rate = fx.rate(conn, r["orig_currency"], day)
        out.fx.append(
            FxItem(
                txn_id=int(r["id"]),
                day=day,
                description=r["description"] or "",
                amount=Decimal(r["amount"]),
                orig=Decimal(r["orig_amount"]),
                currency=r["orig_currency"],
                nbp=rate[1] if rate else None,
            )
        )
    for r in conn.execute(
        "SELECT id, COALESCE(tx_date, booking_date) AS day, description, amount FROM txn "
        "WHERE status = 'BOOK' AND kind = ? "
        "AND COALESCE(tx_date, booking_date) >= ? AND COALESCE(tx_date, booking_date) < ? "
        "ORDER BY day DESC, id DESC",
        (Kind.FEE.value, *span),
    ):
        out.fee_items.append(
            Fee(
                int(r["id"]),
                date.fromisoformat(r["day"]),
                r["description"] or "",
                Decimal(r["amount"]),
            )
        )
    return out


def months(conn: sqlite3.Connection, start: date, end: date) -> list[Costs]:
    """Koszty miesiąc po miesiącu od `start` (1. dzień miesiąca) do `end` (wyłącznie)."""
    out = []
    while start < end:
        nxt = add_months(start, 1)
        out.append(build(conn, start, min(nxt, end)))
        start = nxt
    return out


def csv_until(conn: sqlite3.Connection) -> date | None:
    """Ostatni dzień rozliczenia w zaimportowanym CSV karty — do niego znamy kwoty walutowe."""
    r = conn.execute(
        "SELECT max(r.settle_date) FROM csv_row r "
        "JOIN account_alias a ON a.source = 'csv_number' AND a.value = r.number "
        "JOIN account acc ON acc.id = a.account_id WHERE acc.kind = 'card'"
    ).fetchone()
    return date.fromisoformat(r[0]) if r and r[0] else None
