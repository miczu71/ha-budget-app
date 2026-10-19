"""Śledzenie promocji bankowych (M22 E5, dawne M17): okres, warunki, postęp, premia do odebrania.

Postęp z księgi tylko dla banku z „millen” w nazwie (`ledger`): liczba zakupów kartą (`payments`)
i suma wpływów (`income`) w okresie całej promocji. Pozostałe warunki (`balance`, `manual`) odhacza
użytkownik. Wypłacona premia trafia do `invest_asset` albo tylko do wpływów.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from budget import card, money
from budget.invest import InvestError, save_asset
from budget.kinds import Kind
from budget.piggy import parse_amount
from budget.storage.db import now_iso

KINDS = ("payments", "income", "balance", "manual")
LEDGER_BANK = "millen"
REMIND_DAYS = 7  # dzwonek: tyle dni przed końcem, gdy warunki niespełnione
INCOME_KINDS = (Kind.TRANSFER_IN.value, Kind.OTHER.value)


class PromoError(InvestError):
    pass


@dataclass(frozen=True)
class Condition:
    id: int
    kind: str
    label: str
    target: Decimal | None
    done: bool
    proposed: bool
    progress: Decimal | None  # z księgi; None = odhaczane ręcznie

    @property
    def met(self) -> bool:
        if self.progress is not None and self.target is not None:
            return self.progress >= self.target
        return self.done


@dataclass(frozen=True)
class Track:
    id: int
    bank: str
    title: str
    start: date
    end: date
    bonus: Decimal | None
    status: str
    paid_to: str | None
    conditions: tuple[Condition, ...]

    @property
    def met(self) -> bool:
        return bool(self.conditions) and all(c.met for c in self.conditions)

    def days_left(self, today: date) -> int:
        return (self.end - today).days

    def remind(self, today: date) -> bool:
        return self.status == "active" and (self.met or 0 <= self.days_left(today) <= REMIND_DAYS)


def _plus_months(day: date, months: int) -> date:
    """Ta sama data za `months` miesięcy (31 stycznia + 1 = ostatni dzień lutego)."""
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def _progress(conn: sqlite3.Connection, r: sqlite3.Row, t: sqlite3.Row) -> Decimal | None:
    if not t["ledger"] or r["kind"] not in ("payments", "income"):
        return None
    start, end = date.fromisoformat(t["start_date"]), date.fromisoformat(t["end_date"])
    if r["kind"] == "payments":
        return Decimal(card.count_purchases(conn, start, end))
    placeholders = ", ".join("?" * len(INCOME_KINDS))
    return money.total(
        row[0]
        for row in conn.execute(
            "SELECT t.amount FROM txn t JOIN account a ON a.id = t.account_id "
            f"WHERE a.kind = 'current' AND t.kind IN ({placeholders}) AND t.status = 'BOOK' "
            "AND t.amount NOT LIKE '-%' AND t.booking_date BETWEEN ? AND ?",
            (*INCOME_KINDS, start.isoformat(), end.isoformat()),
        )
    )


def _track(conn: sqlite3.Connection, t: sqlite3.Row) -> Track:
    conds = tuple(
        Condition(
            r["id"],
            r["kind"],
            r["label"],
            Decimal(r["target"]) if r["target"] else None,
            bool(r["done"]),
            bool(r["proposed"]),
            _progress(conn, r, t),
        )
        for r in conn.execute(
            "SELECT * FROM promo_condition WHERE track_id = ? ORDER BY id", (t["id"],)
        )
    )
    return Track(
        t["id"],
        t["bank"],
        t["title"],
        date.fromisoformat(t["start_date"]),
        date.fromisoformat(t["end_date"]),
        Decimal(t["bonus"]) if t["bonus"] else None,
        t["status"],
        t["paid_to"],
        conds,
    )


def tracks(conn: sqlite3.Connection, *, status: str | None = None) -> list[Track]:
    """Śledzenia od najbliższego końca; `status` None = wszystkie."""
    where, args = ("WHERE status = ?", (status,)) if status else ("", ())
    return [
        _track(conn, t)
        for t in conn.execute(
            f"SELECT * FROM promo_track {where} ORDER BY end_date, id", args
        ).fetchall()
    ]


def start(conn: sqlite3.Connection, offer_id: int, today: date, months: int | None = None) -> int:
    """„Skorzystaj”: śledzenie z oferty (okres = długość promocji, domyślnie 3 mies.)."""
    o = conn.execute("SELECT * FROM invest_offer WHERE id = ?", (offer_id,)).fetchone()
    if o is None:
        raise PromoError("Nie ma takiej oferty.")
    length = months or o["months"] or 3
    end = _plus_months(today, length)
    cur = conn.execute(
        "INSERT INTO promo_track (offer_id, bank, title, start_date, end_date, ledger, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            offer_id,
            o["bank"],
            f"{o['bank']} — {o['kind']}",
            today.isoformat(),
            end.isoformat(),
            int(LEDGER_BANK in o["bank"].lower()),
            now_iso(),
        ),
    )
    return int(cur.lastrowid or 0)


def _track_row(conn: sqlite3.Connection, track_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM promo_track WHERE id = ?", (track_id,)).fetchone()
    if row is None:
        raise PromoError("Nie ma takiego śledzenia.")
    return row  # type: ignore[no-any-return]


def set_bonus(conn: sqlite3.Connection, track_id: int, bonus: str | None) -> None:
    _track_row(conn, track_id)
    value = parse_amount(bonus, "premię")
    conn.execute(
        "UPDATE promo_track SET bonus = ? WHERE id = ?",
        (None if value is None else str(value), track_id),
    )


def add_condition(
    conn: sqlite3.Connection,
    track_id: int,
    kind: str,
    label: str,
    target: str | None = None,
    *,
    proposed: bool = False,
) -> int:
    _track_row(conn, track_id)
    clean = " ".join(label.split())[:120]
    if kind not in KINDS:
        raise PromoError("Wybierz rodzaj warunku.")
    if not clean:
        raise PromoError("Opisz warunek.")
    value = parse_amount(target, "wartość warunku")
    if kind in ("payments", "income") and value is None:
        raise PromoError("Podaj próg warunku, np. 5 płatności albo 1000 zł.")
    cur = conn.execute(
        "INSERT INTO promo_condition (track_id, kind, label, target, proposed) "
        "VALUES (?, ?, ?, ?, ?)",
        (track_id, kind, clean, None if value is None else str(value), int(proposed)),
    )
    return int(cur.lastrowid or 0)


def toggle_condition(conn: sqlite3.Connection, condition_id: int) -> None:
    """Odhaczenie ręczne; zatwierdza też propozycję LLM."""
    cur = conn.execute(
        "UPDATE promo_condition SET done = 1 - done, proposed = 0 WHERE id = ?", (condition_id,)
    )
    if not cur.rowcount:
        raise PromoError("Nie ma takiego warunku.")


def delete_condition(conn: sqlite3.Connection, condition_id: int) -> None:
    conn.execute("DELETE FROM promo_condition WHERE id = ?", (condition_id,))


def set_status(conn: sqlite3.Connection, track_id: int, status: str) -> None:
    if status not in ("failed", "cancelled", "active"):
        raise PromoError("Nieznany status.")
    _track_row(conn, track_id)
    conn.execute("UPDATE promo_track SET status = ? WHERE id = ?", (status, track_id))


def mark_paid(
    conn: sqlite3.Connection, track_id: int, paid_to: str, today: date, asset_kind: str = "account"
) -> None:
    """Premia wypłacona: do aktywów (`asset`) albo tylko do wpływów (`income`)."""
    t = _track_row(conn, track_id)
    if t["status"] != "active":
        raise PromoError("Ta promocja jest już zamknięta.")
    if paid_to not in ("asset", "income"):
        raise PromoError("Wybierz, gdzie trafiła premia.")
    if paid_to == "asset":
        if not t["bonus"]:
            raise PromoError("Najpierw wpisz kwotę premii.")
        save_asset(
            conn,
            None,
            asset_kind,
            f"Premia: {t['title']}"[:60],
            t["bonus"],
            None,
            None,
            None,
            False,
        )
    conn.execute(
        "UPDATE promo_track SET status = 'paid', paid_at = ?, paid_to = ? WHERE id = ?",
        (today.isoformat(), paid_to, track_id),
    )


def register(conn: sqlite3.Connection) -> tuple[Decimal, Decimal]:
    """Rejestr premii: (należne = aktywne ze spełnionymi warunkami, wypłacone)."""
    due = money.total(t.bonus for t in tracks(conn, status="active") if t.met and t.bonus)
    paid = money.total(t.bonus for t in tracks(conn, status="paid") if t.bonus)
    return due, paid


def overdue(conn: sqlite3.Connection, today: date) -> int:
    """Aktywne po terminie z niespełnionymi warunkami -> `failed`; liczba zamkniętych."""
    n = 0
    for t in tracks(conn, status="active"):
        if t.end < today and not t.met:
            set_status(conn, t.id, "failed")
            n += 1
    return n
