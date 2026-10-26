"""Śledzenie promocji bankowych (M22 E5, dawne M17): okres, warunki, postęp, premia do odebrania.

Postęp z księgi tylko dla śledzeń z `ledger`: banku z „millen” w nazwie albo ręcznie wpisanej
edycji (M32 E2). Liczy się liczba zakupów kartą (`payments`) i suma wpływów (`income`) w okresie
całej promocji oraz liczba transakcji bezgotówkowych w bieżącym miesiącu (`cashless`: karta i BLIK
na kontach tego banku, bez przelewów własnych). Pozostałe warunki (`balance`, `manual`) odhacza
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

from budget import card, ledger, money
from budget.invest import InvestError, save_asset
from budget.kinds import PURCHASE_KINDS, Kind
from budget.piggy import PiggyError, parse_amount
from budget.settings import Settings
from budget.spending import month_start
from budget.storage.db import now_iso
from budget.suggest import client
from budget.suggest import engine as suggest
from budget.suggest.client import AIError

KIND_LABELS = {
    "payments": "liczba płatności kartą",
    "cashless": "transakcje bezgotówkowe w miesiącu (karta, BLIK)",
    "income": "suma wpływów (zł)",
    "balance": "saldo na dzień (ręcznie)",
    "manual": "inny krok (ręcznie)",
}
KINDS = tuple(KIND_LABELS)
LEDGER_BANK = "millen"
REMIND_DAYS = 7  # dzwonek: tyle dni przed końcem, gdy warunki niespełnione
INCOME_KINDS = (Kind.TRANSFER_IN.value, Kind.OTHER.value)
CASHLESS_KINDS = tuple(k.value for k in sorted(PURCHASE_KINDS))
CASHLESS_LABEL = "Transakcje bezgotówkowe w miesiącu (karta, BLIK)"
CASHLESS_REMIND_DAYS = (14, 7, 2)  # push przed końcem edycji z niespełnionym licznikiem
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

    @property
    def missing(self) -> int:
        """Ile jeszcze do progu (tylko warunki liczone z księgi)."""
        if self.progress is None or self.target is None:
            return 0
        return max(int(self.target - self.progress), 0)


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

    @property
    def cashless(self) -> Condition | None:
        """Licznik transakcji bezgotówkowych (M32), jeśli śledzenie liczy go z księgi."""
        return next(
            (c for c in self.conditions if c.kind == "cashless" and c.progress is not None), None
        )

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


def count_cashless(conn: sqlite3.Connection, bank: str, start: date, end: date) -> int:
    """Karta i BLIK (zakupy, bez zwrotów i przelewów własnych) na kontach banku w `start`..`end`."""
    placeholders = ", ".join("?" * len(CASHLESS_KINDS))
    return int(
        conn.execute(
            "SELECT count(*) FROM txn t JOIN account a ON a.id = t.account_id "
            f"WHERE a.bank = ? COLLATE NOCASE AND t.kind IN ({placeholders}) "
            "AND t.status = 'BOOK' AND t.amount LIKE '-%' AND t.transfer_group IS NULL "
            "AND t.booking_date BETWEEN ? AND ?",
            (bank, *CASHLESS_KINDS, start.isoformat(), end.isoformat()),
        ).fetchone()[0]
    )


def _ledger_bank(bank: str | None) -> str | None:
    """Nazwa do dopasowania kont księgi: Millennium po `LEDGER_BANK`, inny bank po swojej."""
    if not bank:
        return None
    return LEDGER_BANK if LEDGER_BANK in bank.lower() else bank


def _progress(
    conn: sqlite3.Connection, r: sqlite3.Row, t: sqlite3.Row, today: date
) -> Decimal | None:
    if not t["ledger"] or r["kind"] not in ("payments", "income", "cashless"):
        return None
    start, end = date.fromisoformat(t["start_date"]), date.fromisoformat(t["end_date"])
    if r["kind"] == "cashless":  # miesięczny: bieżący miesiąc przycięty do okresu edycji
        lo, hi = max(month_start(today), start), min(card.last_day(today), end)
        return Decimal(count_cashless(conn, t["bank"], lo, hi))
    if r["kind"] == "payments":
        return Decimal(card.count_purchases(conn, start, end, _ledger_bank(t["bank"])))
    placeholders = ", ".join("?" * len(INCOME_KINDS))
    savings = ledger.savings_transfer_ids(conn)  # przelew z własnych oszczędności to nie wpływ
    return money.total(
        row["amount"]
        for row in conn.execute(
            "SELECT t.id, t.amount FROM txn t JOIN account a ON a.id = t.account_id "
            f"WHERE a.kind = 'current' AND t.kind IN ({placeholders}) AND t.status = 'BOOK' "
            "AND t.amount NOT LIKE '-%' AND t.transfer_group IS NULL "
            "AND t.booking_date BETWEEN ? AND ?",
            (*INCOME_KINDS, start.isoformat(), end.isoformat()),
        )
        if int(row["id"]) not in savings
    )


def _track(conn: sqlite3.Connection, t: sqlite3.Row, today: date) -> Track:
    conds = tuple(
        Condition(
            r["id"],
            r["kind"],
            r["label"],
            Decimal(r["target"]) if r["target"] is not None else None,
            bool(r["done"]),
            bool(r["proposed"]),
            _progress(conn, r, t, today),
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


def tracks(
    conn: sqlite3.Connection, *, status: str | None = None, today: date | None = None
) -> list[Track]:
    """Śledzenia od najbliższego końca; `status` None = wszystkie.

    `today` wyznacza miesiąc liczników miesięcznych (domyślnie dzień systemowy)."""
    today = today or date.today()
    where, args = ("WHERE status = ?", (status,)) if status else ("", ())
    return [
        _track(conn, t, today)
        for t in conn.execute(
            f"SELECT * FROM promo_track {where} ORDER BY end_date, id", args
        ).fetchall()
    ]


def start(conn: sqlite3.Connection, offer_id: int, today: date) -> int:
    """„Skorzystaj”: śledzenie z oferty (okres = długość promocji, domyślnie 3 mies.)."""
    o = conn.execute(
        "SELECT * FROM invest_offer WHERE id = ? AND archived_at IS NULL AND status = 'confirmed'",
        (offer_id,),
    ).fetchone()
    if o is None:
        raise PromoError("Nie ma takiej oferty.")
    if conn.execute(
        "SELECT 1 FROM promo_track WHERE offer_id = ? AND status = 'active'", (offer_id,)
    ).fetchone():
        raise PromoError("Ta oferta jest już śledzona.")
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


def start_edition(
    conn: sqlite3.Connection,
    bank: str,
    title: str,
    start_day: date,
    end_day: date,
    threshold: int,
) -> int:
    """Edycja promocji wpisana ręcznie (M32 E2): okres, próg i licznik transakcji z księgi.

    Parametry edycji to stan wpisany przez użytkownika; parser regulaminu (E3) ich nie ustawia."""
    clean_bank, clean_title = " ".join(bank.split())[:40], " ".join(title.split())[:80]
    if not clean_bank:
        raise PromoError("Podaj bank.")
    banks = {b.casefold(): b for b in known_banks(conn)}
    if clean_bank.casefold() not in banks:
        raise PromoError(f"Nieznany bank: {clean_bank}. Wybierz z listy banków w księdze.")
    clean_bank = banks[clean_bank.casefold()]
    if end_day < start_day:
        raise PromoError("Koniec promocji nie może być przed jej początkiem.")
    if not 1 <= threshold <= 100:
        raise PromoError("Próg transakcji: od 1 do 100.")
    cur = conn.execute(
        "INSERT INTO promo_track (bank, title, start_date, end_date, ledger, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        (
            clean_bank,
            clean_title or f"{clean_bank} — promocja",
            start_day.isoformat(),
            end_day.isoformat(),
            now_iso(),
        ),
    )
    track_id = int(cur.lastrowid or 0)
    add_condition(conn, track_id, "cashless", CASHLESS_LABEL, str(threshold))
    return track_id


def known_banks(conn: sqlite3.Connection) -> list[str]:
    """Banki kont w księdze — podpowiedź dla formularza edycji."""
    return [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT bank FROM account WHERE bank IS NOT NULL AND bank != '' ORDER BY bank"
        )
    ]


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
    if kind in ("payments", "income", "cashless") and value is None:
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
    if _track_row(conn, track_id)["status"] == "paid":
        raise PromoError("Premia jest już odebrana.")
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
    added = 0
    try:
        if found.bonus is not None and not t["bonus"]:
            set_bonus(conn, track_id, str(found.bonus))
    except PiggyError:
        pass  # premia od modelu poza zakresem — użytkownik wpisze ją ręcznie
    for kind, label, target in found.conditions:
        try:
            add_condition(
                conn, track_id, kind, label, None if target is None else str(target), proposed=True
            )
        except PiggyError:
            continue
        added += 1
    return None if added else "AI nie znalazło warunków — dodaj je ręcznie."
