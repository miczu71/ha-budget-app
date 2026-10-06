"""Centrum powiadomień panelu (dzwonek, M5b): wszystko, co czeka na decyzję użytkownika.

Każdy dostawca to jedna funkcja zwracająca karty `Item`; nowe źródło = nowa funkcja
w `PROVIDERS`. Stan liczony na bieżąco, bez „przeczytane” — karta znika, gdy sprawa zostanie
załatwiona (transakcje skategoryzowane, propozycja serii potwierdzona albo odrzucona…).

Uzgodnienie salda (`ledger.check_balances`) jest kosztowne, a dzwonek liczy się przy każdej
stronie — wynik jest zapamiętany, dopóki nie zmienią się transakcje, migawki sald ani baza
kontroli (`BalanceMemo`).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from budget import card, ledger, notifications, review, sessions, sync_service
from budget.recurring import changes, series
from budget.snapshot import Snapshot
from budget.spending import add_months, month_label, month_start

Severity = Literal["info", "warn", "error"]
CONSENT_DAYS = 30  # zgoda kończy się za mniej niż tyle dni → karta (push wg opcji add-onu)


@dataclass(frozen=True)
class Item:
    kind: str
    title: str
    count: int
    link: str  # ścieżka panelu (bez prefiksu Ingress)
    severity: Severity = "info"
    detail: str = ""


@dataclass(frozen=True)
class Context:
    now: datetime
    snap: Snapshot

    @property
    def today(self) -> date:
        return self.now.date()


class BalanceMemo:
    """Ostatni wynik `check_balances` z sygnaturą stanu bazy, od której zależy."""

    def __init__(self) -> None:
        self._key: tuple[object, ...] | None = None
        self._value: list[ledger.BalanceCheck] = []

    def get(self, conn: sqlite3.Connection) -> list[ledger.BalanceCheck]:
        key = tuple(
            conn.execute(
                "SELECT (SELECT count(*) FROM txn), (SELECT max(updated_at) FROM txn), "
                "(SELECT max(fetched_at) FROM balance_snapshot), "
                "(SELECT max(set_at) FROM reconcile_base), (SELECT count(*) FROM csv_row)"
            ).fetchone()
        )
        if key != self._key:
            self._value = ledger.check_balances(conn)
            self._key = key
        return self._value


def uncategorized(conn: sqlite3.Connection, ctx: Context, memo: BalanceMemo) -> list[Item]:
    """Bieżący miesiąc zawsze (gdy ma nieskategoryzowane), poprzedni — dopóki je ma."""
    current = month_start(ctx.today)
    out = []
    for start in (current, add_months(current, -1)):
        end = add_months(start, 1)
        count = int(
            conn.execute(
                "SELECT count(*) FROM txn t JOIN account a ON a.id = t.account_id "
                f"WHERE {review.PENDING_WHERE} AND coalesce(t.tx_date, t.booking_date) >= ? "
                "AND coalesce(t.tx_date, t.booking_date) < ?",
                (start.isoformat(), end.isoformat()),
            ).fetchone()[0]
        )
        if count:
            out.append(
                Item(
                    "uncategorized",
                    f"Bez kategorii — {month_label(start)}",
                    count,
                    f"/review?month={start:%Y-%m}",
                    "warn" if start < current else "info",
                    "Transakcje czekają na kategorię w kolejce „Do przejrzenia”.",
                )
            )
    return out


def operational(conn: sqlite3.Connection, ctx: Context, memo: BalanceMemo) -> list[Item]:
    """Zgoda bankowa, nieudane synchronizacje, rozbieżność uzgodnienia salda."""
    alerts = notifications.evaluate(
        sessions.current(conn),
        failures=sync_service.consecutive_failures(conn),
        manual_sync_needed=sync_service.manual_sync_needed(conn),
        warning_days=CONSENT_DAYS,
        now=ctx.now,
        failures_to_alert=1,
    )
    titles = {
        "session_inactive": ("Zgoda bankowa nieaktywna", "/bank", "error"),
        "consent_expiring": ("Zgoda bankowa wkrótce wygasa", "/bank", "warn"),
        "sync_failures": ("Nieudane synchronizacje", "/status", "error"),
        "manual_sync": ("Synchronizacja niepełna", "/status", "warn"),
    }
    out = []
    for alert in alerts:
        title, link, severity = titles[alert.key]
        count = sync_service.consecutive_failures(conn) if alert.key == "sync_failures" else 1
        out.append(Item(alert.key, title, count, link, severity, alert.message))  # type: ignore[arg-type]
    bad = [c for c in memo.get(conn) if not c.ok]
    if bad:
        out.append(
            Item(
                "balance",
                "Rozbieżność uzgodnienia salda",
                len(bad),
                "/#reconcile",
                "warn",
                "Saldo z banku nie zgadza się z księgą — szczegóły na ekranie Status.",
            )
        )
    return out


def new_series(conn: sqlite3.Connection, ctx: Context, memo: BalanceMemo) -> list[Item]:
    count = series.count_proposed(conn)
    if not count:
        return []
    return [
        Item(
            "series_proposed",
            "Nowe płatności cykliczne",
            count,
            "/recurring",
            "info",
            "Wykryte serie czekają na potwierdzenie albo odrzucenie.",
        )
    ]


SERIES_CHANGES = {
    changes.AMOUNT: ("series_amount", "Inna kwota płatności cyklicznej", "info"),
    changes.LATE: ("series_late", "Spóźniona płatność cykliczna", "warn"),
    changes.STOPPED: ("series_stopped", "Płatność cykliczna chyba ustała", "warn"),
}


def series_changes(conn: sqlite3.Connection, ctx: Context, memo: BalanceMemo) -> list[Item]:
    """Jedna karta na rodzaj zmiany serii (szczegóły i decyzje: `/recurring#changes`)."""
    found = changes.for_db(ctx.snap, ctx.today)
    out = []
    for kind, (item_kind, title, severity) in SERIES_CHANGES.items():
        mine = [c for c in found if c.kind == kind]
        if mine:
            names = ", ".join(sorted({c.series.name for c in mine}))
            out.append(
                Item(item_kind, title, len(mine), "/recurring#changes", severity, names)  # type: ignore[arg-type]
            )
    return out


def card_payments(conn: sqlite3.Connection, ctx: Context, memo: BalanceMemo) -> list[Item]:
    """Ostatnie dni miesiąca, a płatności kartą kredytową mniej niż próg zwolnienia z opłaty."""
    if not card.in_remind_window(ctx.today):
        return []
    cm = card.month_status(conn, ctx.today)
    if not cm or not cm.missing:
        return []
    period = f"date_from={cm.month.isoformat()}&date_to={cm.last_day.isoformat()}"
    return [
        Item(
            "card_payments",
            f"Karta kredytowa: brakuje {cm.missing} płatności",
            cm.missing,
            f"/transactions?account={cm.account_id}&{period}",
            "warn",
            f"Do {cm.last_day:%d.%m} potrzeba {cm.threshold} płatności kartą, inaczej bank "
            "pobierze opłatę. BLIK się nie liczy.",
        )
    ]


Provider = Callable[[sqlite3.Connection, Context, BalanceMemo], list[Item]]
PROVIDERS: tuple[Provider, ...] = (
    operational,
    uncategorized,
    new_series,
    series_changes,
    card_payments,
)
SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}


def items(snap: Snapshot, now: datetime, memo: BalanceMemo) -> list[Item]:
    ctx = Context(now, snap)
    out = [item for provider in PROVIDERS for item in provider(snap.conn, ctx, memo)]
    return sorted(out, key=lambda i: SEVERITY_ORDER[i.severity])
