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
from budget.money import CENT, ZERO
from budget.spending import add_months, month_start

_PCT = Decimal("0.1")
_DAY = "COALESCE(tx_date, booking_date)"


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
    def base(self) -> Decimal | None:
        """Wartość po kursie NBP (None: brak kursu)."""
        return None if self.nbp is None else abs(self.orig * self.nbp)

    @property
    def cost(self) -> Decimal | None:
        if self.nbp is None:
            return None
        return (-(self.amount - self.orig * self.nbp)).quantize(CENT)

    @property
    def pct(self) -> Decimal | None:
        """Koszt w % wartości po kursie NBP."""
        return _pct(self.cost, self.base)


@dataclass(frozen=True)
class Fee:
    txn_id: int
    day: date
    description: str
    amount: Decimal  # ze znakiem: obciążenie ujemne, zwrot opłaty dodatni


def _pct(cost: Decimal | None, base: Decimal | None) -> Decimal | None:
    return None if cost is None or not base else (cost / base * 100).quantize(_PCT)


@dataclass
class Costs:
    start: date
    fx: list[FxItem] = field(default_factory=list)
    fee_items: list[Fee] = field(default_factory=list)

    @property
    def priced(self) -> list[FxItem]:
        return [i for i in self.fx if i.cost is not None]

    @property
    def fx_cost(self) -> Decimal:
        return sum((i.cost for i in self.priced if i.cost is not None), ZERO)

    @property
    def fx_volume(self) -> Decimal:
        """Wartość transakcji walutowych po kursie NBP (podstawa średniego %)."""
        return sum((i.base for i in self.priced if i.base is not None), ZERO).quantize(CENT)

    @property
    def fx_pct(self) -> Decimal | None:
        return _pct(self.fx_cost, self.fx_volume)

    @property
    def fees(self) -> Decimal:
        return -sum((f.amount for f in self.fee_items), ZERO)

    @property
    def missing(self) -> int:
        return len(self.fx) - len(self.priced)

    @property
    def total(self) -> Decimal:
        return self.fx_cost + self.fees


def build(conn: sqlite3.Connection, start: date, end: date) -> Costs:
    """Koszty transakcji zaksięgowanych w [start, end) według daty transakcji (od najnowszych)."""
    out = Costs(start)
    span = f"status = 'BOOK' AND currency = 'PLN' AND {_DAY} >= ? AND {_DAY} < ?"
    args = (start.isoformat(), end.isoformat())
    rates = fx.Rates(conn)
    for r in conn.execute(
        f"SELECT id, {_DAY} AS day, description, amount, orig_amount, orig_currency FROM txn "
        f"WHERE {span} AND {fx.IS_FX} AND orig_amount IS NOT NULL ORDER BY day DESC, id DESC",
        args,
    ):
        day = date.fromisoformat(r["day"])
        out.fx.append(
            FxItem(
                txn_id=int(r["id"]),
                day=day,
                description=r["description"] or "",
                amount=Decimal(r["amount"]),
                orig=Decimal(r["orig_amount"]),
                currency=r["orig_currency"],
                nbp=rates.get(r["orig_currency"], day),
            )
        )
    for r in conn.execute(
        f"SELECT id, {_DAY} AS day, description, amount FROM txn "
        f"WHERE {span} AND kind = ? ORDER BY day DESC, id DESC",
        (*args, Kind.FEE.value),
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


def months(c: Costs, end: date) -> list[Costs]:
    """Koszty `c` podzielone na miesiące od `c.start` do `end` (wyłącznie), od najnowszego."""
    out: dict[date, Costs] = {}
    m = c.start
    while m < end:
        out[m] = Costs(m)
        m = add_months(m, 1)
    for i in c.fx:
        if (bucket := out.get(month_start(i.day))) is not None:
            bucket.fx.append(i)
    for f in c.fee_items:
        if (bucket := out.get(month_start(f.day))) is not None:
            bucket.fee_items.append(f)
    return list(reversed(out.values()))


def csv_until(conn: sqlite3.Connection) -> date | None:
    """Ostatni dzień rozliczenia w zaimportowanym CSV karty — do niego znamy kwoty walutowe."""
    r = conn.execute(
        "SELECT max(r.settle_date) FROM csv_row r "
        "JOIN account_alias a ON a.source = 'csv_number' AND a.value = r.number "
        "JOIN account acc ON acc.id = a.account_id WHERE acc.kind = 'card'"
    ).fetchone()
    return date.fromisoformat(r[0]) if r and r[0] else None
