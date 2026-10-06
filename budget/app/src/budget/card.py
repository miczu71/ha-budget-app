"""Płatności kartą kredytową (M15): karta bezpłatna przy 5 płatnościach w miesiącu.

Cennik: opłaty nie ma, „jeśli w poprzednim miesiącu zapłacisz min. 5 razy kartą”; BLIK się nie
liczy, a każda karta (główna, dodatkowa) liczona jest osobno. API nie podaje numeru karty, więc
płatność przypisuje użytkownik do osoby (E2, `card_holder`); nieprzypisana nie liczy się nikomu.
Historię przypisuje eksport CSV z Millenetu (E3): numer karty → osoba. Eksport ma blok całego konta
karty pod jednym numerem i blok płatności jednej karty pod drugim — wygrywa najwęższy blok.
Bez osób w bazie licznik jest wspólny dla konta karty (E1).
API ma tylko datę księgowania (zakup zwykle 2 dni wcześniej), a cennik nie mówi, którą datę
bank bierze — liczba to mniejsza z dwóch: po dacie księgowania i po dacie księgowania − 2 dni.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from budget.kinds import Kind
from budget.spending import add_months, month_start
from budget.storage.db import now_iso

THRESHOLD = 5
BOOKING_LAG = timedelta(days=2)
REMIND_DAYS = (5, 1)  # przypomnienie na telefon tyle dni przed ostatnim dniem miesiąca
PAYMENT_WHERE = (
    f"t.account_id = ? AND t.kind = '{Kind.CARD.value}' AND t.status = 'BOOK' "
    "AND t.amount LIKE '-%'"
)


class CardError(ValueError):
    """Błąd danych od użytkownika (komunikat do panelu)."""


def last_day(today: date) -> date:
    return add_months(month_start(today), 1) - timedelta(days=1)


def days_to_end(today: date) -> int:
    return (last_day(today) - today).days


def remind_today(today: date) -> bool:
    """Dzień przypomnienia na telefon (bez zapytań do bazy)."""
    return days_to_end(today) in REMIND_DAYS


def in_remind_window(today: date) -> bool:
    """Od pierwszego przypomnienia do końca miesiąca — karta w dzwonku."""
    return days_to_end(today) <= max(REMIND_DAYS)


@dataclass(frozen=True)
class HolderCount:
    id: int  # 0 = wszystkie płatności, gdy nie ma jeszcze osób (licznik wspólny, E1)
    name: str
    count: int
    threshold: int = THRESHOLD

    @property
    def missing(self) -> int:
        return max(self.threshold - self.count, 0)


@dataclass(frozen=True)
class CardMonth:
    month: date
    holders: tuple[HolderCount, ...]  # bez osób w bazie: jedna pozycja „Razem”
    shared: bool  # licznik wspólny (brak osób)
    count: int  # wszystkie płatności miesiąca (przypisane i nie)
    unassigned: int = 0
    threshold: int = THRESHOLD

    @property
    def missing(self) -> int:
        return sum(h.missing for h in self.holders)

    @property
    def needs_action(self) -> bool:
        return bool(self.missing or self.unassigned)

    @property
    def last_day(self) -> date:
        return last_day(self.month)


def card_account(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT id FROM account WHERE kind = 'card' ORDER BY id LIMIT 1").fetchone()
    return None if row is None else int(row[0])


def holders(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM card_holder ORDER BY id").fetchall()


def _name(name: str) -> str:
    clean = " ".join(name.split())[:40]
    if not clean:
        raise CardError("Podaj imię.")
    return clean


def add_holder(conn: sqlite3.Connection, name: str) -> int:
    try:
        cur = conn.execute(
            "INSERT INTO card_holder (name, created_at) VALUES (?, ?)", (_name(name), now_iso())
        )
    except sqlite3.IntegrityError as exc:
        raise CardError("Taka osoba już jest.") from exc
    return int(cur.lastrowid or 0)


def rename_holder(conn: sqlite3.Connection, holder_id: int, name: str) -> None:
    try:
        cur = conn.execute("UPDATE card_holder SET name = ? WHERE id = ?", (_name(name), holder_id))
    except sqlite3.IntegrityError as exc:
        raise CardError("Taka osoba już jest.") from exc
    if not cur.rowcount:
        raise CardError("Nie ma takiej osoby.")


def assign(conn: sqlite3.Connection, txn_id: int, holder_id: int) -> None:
    """Przypisanie płatności kartą do osoby (także zmiana osoby)."""
    account = card_account(conn)
    if (
        account is None
        or not conn.execute(
            f"SELECT 1 FROM txn t WHERE t.id = ? AND {PAYMENT_WHERE}", (txn_id, account)
        ).fetchone()
    ):
        raise CardError("To nie jest płatność kartą kredytową.")
    if not conn.execute("SELECT 1 FROM card_holder WHERE id = ?", (holder_id,)).fetchone():
        raise CardError("Nie ma takiej osoby.")
    conn.execute("UPDATE txn SET card_holder_id = ? WHERE id = ?", (holder_id, txn_id))


CARD_NUMBERS = "SELECT value FROM account_alias WHERE source = 'csv_number' AND account_id = ?"


def csv_numbers(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Numery kart z eksportu CSV powiązane z kontem karty, z liczbą wierszy (rosnąco)."""
    account = card_account(conn)
    if account is None:
        return []
    return conn.execute(
        f"SELECT number, count(*) AS n FROM csv_row WHERE number IN ({CARD_NUMBERS}) "
        "GROUP BY number ORDER BY n, number",
        (account,),
    ).fetchall()


def set_csv_number(conn: sqlite3.Connection, holder_id: int, number: str | None) -> None:
    if number is not None and number not in {r["number"] for r in csv_numbers(conn)}:
        raise CardError("Nie ma takiego numeru w imporcie CSV.")
    try:
        cur = conn.execute(
            "UPDATE card_holder SET csv_number = ? WHERE id = ?", (number, holder_id)
        )
    except sqlite3.IntegrityError as exc:
        raise CardError("Ten numer karty ma już inna osoba.") from exc
    if not cur.rowcount:
        raise CardError("Nie ma takiej osoby.")


def backfill_from_csv(conn: sqlite3.Connection) -> int | None:
    """Osoba dla płatności bez osoby z numeru karty w CSV; liczba przypisanych.

    None, dopóki nie każdy numer karty z CSV ma osobę — sam numer bloku całego konta przypisałby
    jednej osobie także płatności drugiej karty. Najwęższy blok pierwszy, a ręczne i wcześniejsze
    przypisania zostają (`card_holder_id IS NULL`). Wołane w `ledger.rebuild_derived`.
    """
    account = card_account(conn)
    numbers = csv_numbers(conn)
    by_number = {h["csv_number"]: h["id"] for h in holders(conn)}
    if account is None or not numbers or any(r["number"] not in by_number for r in numbers):
        return None
    return sum(
        conn.execute(
            "UPDATE txn AS t SET card_holder_id = ? WHERE t.card_holder_id IS NULL "
            f"AND {PAYMENT_WHERE} AND t.id IN (SELECT coalesce(r.txn_id, b.txn_id) FROM csv_row r "
            "LEFT JOIN csv_row b ON r.txn_id IS NULL AND b.row_key = r.row_key "
            f"AND b.txn_id IS NOT NULL AND b.number IN ({CARD_NUMBERS}) WHERE r.number = ?)",
            (by_number[r["number"]], account, account, r["number"]),
        ).rowcount
        for r in numbers
    )


def payments(conn: sqlite3.Connection, month: date) -> list[sqlite3.Row]:
    """Płatności kartą zaksięgowane w miesiącu, od najnowszych (ekran „Karta”)."""
    account = card_account(conn)
    if account is None:
        return []
    start = month_start(month)
    return conn.execute(
        "SELECT t.id, t.booking_date, t.amount, t.currency, t.merchant, t.description, "
        f"t.card_holder_id FROM txn t WHERE {PAYMENT_WHERE} "
        "AND t.booking_date >= ? AND t.booking_date < ? ORDER BY t.booking_date DESC, t.id DESC",
        (account, start.isoformat(), add_months(start, 1).isoformat()),
    ).fetchall()


def month_status(conn: sqlite3.Connection, today: date) -> CardMonth | None:
    """Miesiąc daty `today`; None, gdy nie ma konta karty kredytowej."""
    account = card_account(conn)
    if account is None:
        return None
    start = month_start(today)
    end = add_months(start, 1)
    rows = conn.execute(
        "SELECT t.card_holder_id, coalesce(sum(t.booking_date < ?), 0), "
        f"coalesce(sum(t.booking_date >= ?), 0) FROM txn t WHERE {PAYMENT_WHERE} "
        "AND t.booking_date >= ? AND t.booking_date < ? GROUP BY t.card_holder_id",
        (
            end.isoformat(),
            (start + BOOKING_LAG).isoformat(),
            account,
            start.isoformat(),
            (end + BOOKING_LAG).isoformat(),
        ),
    ).fetchall()
    by_holder = {r[0]: (int(r[1]), int(r[2])) for r in rows}
    total = min(sum(b for b, _ in by_holder.values()), sum(p for _, p in by_holder.values()))
    people = tuple(
        HolderCount(h["id"], h["name"], min(by_holder.get(h["id"], (0, 0)))) for h in holders(conn)
    )
    if not people:
        return CardMonth(start, (HolderCount(0, "Razem", total),), True, total)
    return CardMonth(start, people, False, total, by_holder.get(None, (0, 0))[0])
