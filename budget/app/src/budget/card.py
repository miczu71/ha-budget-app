"""Licznik płatności kartą kredytową (M15 E1): karta bezpłatna przy 5 płatnościach w miesiącu.

Cennik: opłaty nie ma, „jeśli w poprzednim miesiącu zapłacisz min. 5 razy kartą”; BLIK się nie
liczy, a każda karta (główna, dodatkowa) liczona jest osobno. API nie podaje numeru karty, więc
licznik jest wspólny dla konta karty — „brakuje” jest zawsze trafne, „spełnione” dotyczy sumy.
API ma tylko datę księgowania (zakup zwykle 2 dni wcześniej), a cennik nie mówi, którą datę
bank bierze — liczba to mniejsza z dwóch: po dacie księgowania i po dacie księgowania − 2 dni.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from budget.kinds import Kind
from budget.spending import add_months, month_start

THRESHOLD = 5
BOOKING_LAG = timedelta(days=2)
REMIND_DAYS = (5, 1)  # przypomnienie na telefon tyle dni przed ostatnim dniem miesiąca


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
class CardMonth:
    account_id: int
    month: date
    count: int
    threshold: int = THRESHOLD

    @property
    def missing(self) -> int:
        return max(self.threshold - self.count, 0)

    @property
    def last_day(self) -> date:
        return last_day(self.month)


def month_status(conn: sqlite3.Connection, today: date) -> CardMonth | None:
    """Bieżący miesiąc; None, gdy nie ma konta karty kredytowej."""
    row = conn.execute("SELECT id FROM account WHERE kind = 'card' ORDER BY id LIMIT 1").fetchone()
    if row is None:
        return None
    start = month_start(today)
    end = add_months(start, 1)
    by_booking, by_purchase = conn.execute(
        "SELECT coalesce(sum(booking_date < ?), 0), coalesce(sum(booking_date >= ?), 0) "
        "FROM txn WHERE account_id = ? AND kind = ? AND status = 'BOOK' AND amount LIKE '-%' "
        "AND booking_date >= ? AND booking_date < ?",
        (
            end.isoformat(),
            (start + BOOKING_LAG).isoformat(),
            row[0],
            Kind.CARD.value,
            start.isoformat(),
            (end + BOOKING_LAG).isoformat(),
        ),
    ).fetchone()
    return CardMonth(row[0], start, min(by_booking, by_purchase))
