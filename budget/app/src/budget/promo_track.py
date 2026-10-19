"""Śledzenie promocji bankowych (M22 E5, dawne M17): okres, warunki, postęp, premia do odebrania.

Postęp z księgi tylko dla banku z „millen” w nazwie (`ledger`): liczba zakupów kartą (`payments`)
i suma wpływów (`income`) w okresie całej promocji. Pozostałe warunki (`balance`, `manual`) odhacza
użytkownik. Wypłacona premia trafia do `invest_asset` albo tylko do wpływów.
"""

from __future__ import annotations

import calendar
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from budget import card, money
from budget.invest import InvestError, save_asset
from budget.kinds import Kind
from budget.piggy import parse_amount
from budget.settings import Settings
from budget.storage.db import now_iso
from budget.suggest import client
from budget.suggest import engine as suggest
from budget.suggest.client import AIError

KIND_LABELS = {
    "payments": "liczba płatności kartą",
    "income": "suma wpływów (zł)",
    "balance": "saldo na dzień (ręcznie)",
    "manual": "inny krok (ręcznie)",
}
KINDS = tuple(KIND_LABELS)
LEDGER_BANK = "millen"
REMIND_DAYS = 7  # dzwonek: tyle dni przed końcem, gdy warunki niespełnione
INCOME_KINDS = (Kind.TRANSFER_IN.value, Kind.OTHER.value)
USAGE_KEY = "invest_usage"
SCHEMA_NAME = "warunki_promocji"
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "bonus": {"type": "number"},
        "conditions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "label": {"type": "string"},
                    "target": {"type": "number"},
                },
                "required": ["kind", "label", "target"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["bonus", "conditions"],
    "additionalProperties": False,
}


class PromoError(InvestError):
    pass


@dataclass(frozen=True)
class Proposal:
    bonus: Decimal | None
    conditions: tuple[tuple[str, str, Decimal | None], ...]  # (rodzaj, opis, próg)


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
    offer_id: int | None
    bank: str
    title: str
    start: date
    end: date
    bonus: Decimal | None
    status: str
    conditions: tuple[Condition, ...]

    @property
    def met(self) -> bool:
        return bool(self.conditions) and all(c.met for c in self.conditions)

    def days_left(self, today: date) -> int:
        return (self.end - today).days

    def remind(self, today: date) -> bool:
        """Dzwonek: warunki spełnione (odbierz premię) albo koniec blisko lub minął (zamknij)."""
        return self.status == "active" and (self.met or self.days_left(today) <= REMIND_DAYS)


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
        t["offer_id"],
        t["bank"],
        t["title"],
        date.fromisoformat(t["start_date"]),
        date.fromisoformat(t["end_date"]),
        Decimal(t["bonus"]) if t["bonus"] else None,
        t["status"],
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


def start(conn: sqlite3.Connection, offer_id: int, today: date) -> int:
    """„Skorzystaj”: śledzenie z oferty (okres = długość promocji, domyślnie 3 mies.)."""
    o = conn.execute("SELECT * FROM invest_offer WHERE id = ?", (offer_id,)).fetchone()
    if o is None:
        raise PromoError("Nie ma takiej oferty.")
    length = o["months"] or 3
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


def confirm_condition(conn: sqlite3.Connection, condition_id: int) -> None:
    """Zatwierdzenie propozycji LLM bez zmiany odhaczenia."""
    cur = conn.execute("UPDATE promo_condition SET proposed = 0 WHERE id = ?", (condition_id,))
    if not cur.rowcount:
        raise PromoError("Nie ma takiego warunku.")


def delete_condition(conn: sqlite3.Connection, condition_id: int) -> None:
    conn.execute("DELETE FROM promo_condition WHERE id = ?", (condition_id,))


def set_status(conn: sqlite3.Connection, track_id: int, status: str) -> None:
    if status not in ("failed", "cancelled", "active"):
        raise PromoError("Nieznany status.")
    _track_row(conn, track_id)
    conn.execute("UPDATE promo_track SET status = ? WHERE id = ?", (status, track_id))


def mark_paid(conn: sqlite3.Connection, track_id: int, paid_to: str, today: date) -> None:
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
            asset_id=None,
            kind="account",
            name=f"Premia: {t['title']}"[:60],
            amount=t["bonus"],
            rate=None,
            start=None,
            maturity=None,
            ike=False,
        )
    conn.execute(
        "UPDATE promo_track SET status = 'paid', paid_at = ?, paid_to = ? WHERE id = ?",
        (today.isoformat(), paid_to, track_id),
    )


def register(items: Sequence[Track]) -> tuple[Decimal, Decimal]:
    """Rejestr premii: (należne = aktywne ze spełnionymi warunkami, wypłacone)."""
    due = money.total(t.bonus for t in items if t.status == "active" and t.met and t.bonus)
    paid = money.total(t.bonus for t in items if t.status == "paid" and t.bonus)
    return due, paid


# --- propozycja warunków i premii od modelu ---------------------------------------------------


def build_prompt(text: str) -> str:
    return (
        "Z opisu promocji bankowej wyciągnij premię w złotych i warunki jej otrzymania. "
        "Niczego nie zgaduj: gdy opis nie podaje premii, bonus = 0, a gdy nie podaje warunków, "
        "zwróć pustą listę. Pola warunku: kind (payments = liczba płatności kartą, income = "
        "suma wpływów na konto w zł, balance = saldo utrzymane na dany dzień, manual = inny krok, "
        "np. aktywacja aplikacji), label (opis jednym zdaniem po polsku), target (liczba "
        "płatności albo kwota w zł; 0 dla balance i manual).\n\n"
        f"Opis promocji: {text}"
    )


def parse_proposal(result: dict[str, Any]) -> Proposal:
    """Odpowiedź modelu → tylko pozycje, które przechodzą walidację (resztę odrzucamy po cichu)."""
    bonus: Decimal | None
    try:
        bonus = Decimal(str(result.get("bonus")))
    except InvalidOperation:
        bonus = None
    if bonus is None or not bonus.is_finite() or not 0 < bonus < 100_000:
        bonus = None
    out = []
    for raw in result.get("conditions") or []:
        if not isinstance(raw, dict) or raw.get("kind") not in KINDS:
            continue
        label = " ".join(str(raw.get("label", "")).split())[:120]
        try:
            target: Decimal | None = Decimal(str(raw.get("target")))
        except InvalidOperation:
            target = None
        if target is not None and not (target.is_finite() and 0 < target < 1_000_000):
            target = None
        if not label or (raw["kind"] in ("payments", "income") and target is None):
            continue
        out.append((raw["kind"], label, target))
    return Proposal(bonus, tuple(out))


async def propose(
    conn: sqlite3.Connection,
    settings: Settings,
    today: date,
    track_id: int,
    call: suggest.Call = client.complete,
) -> str | None:
    """Wstępne warunki i premia z tekstu oferty (jako propozycje do sprawdzenia).

    Zwraca komunikat dla użytkownika, gdy się nie udało; śledzenie zostaje bez warunków."""
    t = _track_row(conn, track_id)
    offer = conn.execute("SELECT * FROM invest_offer WHERE id = ?", (t["offer_id"],)).fetchone()
    text = (offer["conditions"] if offer else "") or ""
    if not text.strip():
        return "Oferta nie ma opisu warunków — dodaj je ręcznie."
    if not settings.ai_enabled or settings.invest_daily_calls <= 0:
        return "Podpowiedzi AI są wyłączone — dodaj warunki ręcznie."
    if int(suggest.usage(conn, today, USAGE_KEY).get("calls", 0)) >= settings.invest_daily_calls:
        return "Dobowy limit zapytań do AI wyczerpany — dodaj warunki ręcznie."
    try:
        result = await suggest.metered_call(
            conn,
            settings,
            today,
            call,
            key=USAGE_KEY,
            prompt=build_prompt(text),
            schema=SCHEMA,
            schema_name=SCHEMA_NAME,
        )
    except AIError:
        return "AI nie odpowiedziało — dodaj warunki ręcznie."
    found = parse_proposal(result)
    if found.bonus is not None and not t["bonus"]:
        set_bonus(conn, track_id, str(found.bonus))
    for kind, label, target in found.conditions:
        add_condition(
            conn, track_id, kind, label, None if target is None else str(target), proposed=True
        )
    return None if found.conditions else "AI nie znalazło warunków — dodaj je ręcznie."
