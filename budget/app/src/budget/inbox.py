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

from budget import (
    card,
    ledger,
    loan,
    loan_sim,
    money,
    notifications,
    promo_watch,
    review,
    savings,
    sessions,
    summary,
    sync_service,
    wibor,
)
from budget.forecast import Forecast
from budget.recurring import changes, series
from budget.snapshot import Snapshot
from budget.spending import add_months, month_label, month_start
from budget.storage import db

Severity = Literal["info", "warn", "error"]
DISMISSED_KEY = "inbox_dismissed"  # kv: klucze ręcznie ukrytych kart (`Item.key`)
DELETED_KEY = "inbox_deleted"  # kv: klucze kart usuniętych na stałe (bez przywracania)
CONSENT_DAYS = 30  # zgoda kończy się za mniej niż tyle dni → karta (push wg opcji add-onu)


@dataclass(frozen=True)
class Item:
    kind: str
    title: str
    count: int
    link: str  # ścieżka panelu (bez prefiksu Ingress)
    severity: Severity = "info"
    detail: str = ""

    @property
    def key(self) -> str:
        """Tożsamość karty przy ukrywaniu: zmiana tytułu (np. nowa edycja) to nowa karta."""
        return f"{self.kind}|{self.title}"


@dataclass(frozen=True)
class Context:
    now: datetime
    snap: Snapshot
    forecast: Forecast | None = None

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
    """Płatności kartą do przypisania osobie (zawsze) i braki do progu (ostatnie dni miesiąca)."""
    cm = card.month_status(conn, ctx.today)
    if not cm:
        return []
    window = card.in_remind_window(ctx.today)
    out = []
    if cm.unassigned:
        out.append(
            Item(
                "card_assign",
                "Karta kredytowa: płatności do przypisania",
                cm.unassigned,
                "/card",
                "warn" if window else "info",
                "Nieprzypisana płatność kartą nie liczy się do progu zwolnienia z opłaty nikomu.",
            )
        )
    if window:
        detail = (
            f"Do {cm.last_day:%d.%m} potrzeba {cm.threshold} płatności kartą, inaczej bank "
            "pobierze opłatę. BLIK się nie liczy."
        )
        out += [
            Item(
                "card_payments",
                f"Karta kredytowa: {'' if cm.shared else h.name + ' — '}brakuje płatności",
                h.missing,
                "/card",
                "warn",
                detail,
            )
            for h in cm.holders
            if h.missing
        ]
    return out


def card_due(conn: sqlite3.Connection, ctx: Context, memo: BalanceMemo) -> list[Item]:
    """Kwota z zamkniętego cyklu karty do spłaty — od 1. dnia, warn od przypomnień i po terminie."""
    cd = card.due_status(conn, ctx.today)
    if not cd or not cd.left:
        return []
    if cd.overdue:
        title, detail = "Karta kredytowa: spłata po terminie", f"Termin minął {cd.due:%d.%m}."
    else:
        title = "Karta kredytowa: do spłaty"
        detail = f"Termin {cd.due:%d.%m} — {summary.when(cd.days_left)}."
    return [
        Item(
            "card_due",
            f"{title} {money.pl(cd.left, 'PLN')}",
            1,
            "/card",
            "warn" if cd.soon else "info",
            detail + " Kwota liczona ostrożnie — może być nieco wyższa niż w banku.",
        )
    ]


def forecast_low(conn: sqlite3.Connection, ctx: Context, memo: BalanceMemo) -> list[Item]:
    """Najniższe wolne środki przed wypłatą poniżej bufora (`forecast_buffer`, domyślnie 0)."""
    fc = ctx.forecast
    if fc is None or fc.low_day is None or not fc.below_buffer:
        return []
    title = (
        "Prognoza: wolne środki poniżej bufora" if fc.buffer else "Prognoza: zabraknie do wypłaty"
    )
    detail = f"Najniższy punkt {fc.low_day:%d.%m}: {summary.zl(fc.low)}"
    if fc.buffer:
        detail += f" (bufor {summary.zl(fc.buffer)})"
    return [Item("forecast_low", title, 1, "/", "warn", detail)]


PIGGY_REMIND_DAYS = 5  # przypomnienie o odłożeniu do skarbonek tyle dni przed wypłatą (M10 E1)


def piggy_transfer(conn: sqlite3.Connection, ctx: Context, memo: BalanceMemo) -> list[Item]:
    """Nieprzelane odłożenie do skarbonek, gdy do wypłaty zostało mniej niż `PIGGY_REMIND_DAYS`."""
    fc = ctx.forecast
    if fc is None or fc.payday is None or not fc.piggy_out or fc.days_left >= PIGGY_REMIND_DAYS:
        return []
    detail = f"Do wypłaty {fc.payday:%d.%m} przelej na konta-cele {summary.zl(fc.piggy_out)}."
    return [Item("piggy_transfer", "Odłóż do skarbonek", 1, "/piggy", "info", detail)]


def savings_promo(conn: sqlite3.Connection, ctx: Context, memo: BalanceMemo) -> list[Item]:
    """Promocyjna stopa konta oszczędnościowego kończy się za `PROMO_REMIND_DAYS[0]` dni."""
    out = []
    for acc in savings.all_accounts(conn):
        days = acc.promo_days_left(ctx.today)
        if days is None or days > savings.PROMO_REMIND_DAYS[0]:
            continue
        detail = f"Stopa {acc.promo_rate}% do {acc.promo_until:%d.%m}"
        detail += f", potem {acc.base_rate or 0}% — rozważ przeniesienie środków."
        title = f"Promocja konta „{acc.name}” kończy się {summary.when(days)}"
        out.append(
            Item(
                "savings_promo", title, 1, "/piggy#savings", "warn" if days <= 3 else "info", detail
            )
        )
    return out


PROMO_BELL_DAYS = 10  # karta „wyzeruj KOP” od tylu dni przed początkiem okna badania (E7)


def promo_cards(conn: sqlite3.Connection, ctx: Context, memo: BalanceMemo) -> list[Item]:
    """Monitor edycji promocji Profit: okno badania sald, otwarte przystępowanie, błąd odczytu."""
    watch = promo_watch.load(conn)
    if watch is None:
        return []
    out = []
    link = "/piggy#promo"
    if watch.error_since and (ctx.now - watch.error_since).days >= promo_watch.ERROR_ALERT_DAYS:
        since = f"{watch.error_since:%d.%m}"
        detail = f"Od {since}: {watch.error}. Sprawdź datę badania sald na stronie banku."
        out.append(
            Item(
                "promo_error",
                "Nie mogę odczytać regulaminu promocji Profit",
                1,
                link,
                "warn",
                detail,
            )
        )
    ed, today = watch.edition, ctx.today
    if ed is None:
        return out
    start, end = ed.window()
    if today > ed.deadline:
        detail = (
            f"Badanie sald mogło już być ({start:%d.%m}–{end:%d.%m}); sprawdzę regulamin jutro."
        )
        out.append(
            Item(
                "promo_wait",
                f"Profit: czekam na regulamin edycji {ed.number + 1}",
                1,
                link,
                "info",
                detail,
            )
        )
        return out
    if ed.baseline < today:
        title = f"Profit, edycja {ed.number}: wpłać nowe środki do {ed.deadline:%d.%m}"
        out.append(Item("promo_intake", title, 1, link, "info", "Dzień badania sald już minął."))
    days = ed.days_to_window(today)
    if days <= PROMO_BELL_DAYS:
        title = f"Profit: wyzeruj KOP przed badaniem sald edycji {ed.number + 1}"
        detail = (
            f"Badanie wypadnie prawdopodobnie {start:%d.%m}–{end:%d.%m} (prognoza; datę poda bank)."
        )
        severity: Severity = "warn" if days <= max(summary.PROMO_PUSH_DAYS) else "info"
        out.append(Item("promo_window", title, 1, link, severity, detail))
    return out


def loan_rate(conn: sqlite3.Connection, ctx: Context, memo: BalanceMemo) -> list[Item]:
    """Rata kredytu w księdze inna niż w harmonogramie — zmienił się WIBOR albo marża (M9 E2)."""
    out = []
    for lo in loan.all_loans(conn):
        if lo.series_id is None:
            continue
        live = [s for s in series.all_series(conn, ("active",)) if s.id == lo.series_id]
        paid = series.assign(live, ctx.snap.candidates()).get(lo.series_id, [])
        d = loan.drift(loan.schedule(lo), paid[-1].day, abs(paid[-1].amount)) if paid else None
        if d is None:
            continue
        detail = (
            f"Rata {d.day:%d.%m}: {summary.zl(d.paid)} w banku, {summary.zl(d.expected)} w "
            "harmonogramie. Zmienił się WIBOR lub marża? Wpisz nowy kapitał i stopę."
        )
        out.append(
            Item(
                "loan_rate",
                f"{lo.name}: rata inna niż w harmonogramie",
                1,
                f"/loan?edit={lo.id}#edit-loan",
                "warn",
                detail,
            )
        )
    return out


def loan_reset(conn: sqlite3.Connection, ctx: Context, memo: BalanceMemo) -> list[Item]:
    """Bank zmienił oprocentowanie (WIBOR), a kredyt w panelu jest sprzed zmiany (M9 E4)."""
    out = []
    for lo in loan.all_loans(conn):
        fc = loan_sim.pending(conn, lo, ctx.today)
        if fc is None:
            continue
        detail = (
            f"WIBOR 3M {fc.wibor}% z {fc.quote_day:%d.%m}: rata ≈ {summary.zl(fc.installment)} "
            f"zamiast {summary.zl(fc.current)}. Wpisz nowy kapitał, stopę i ratę z banku."
        )
        title = f"{lo.name}: od {fc.reset:%d.%m} nowe oprocentowanie {fc.rate}%"
        out.append(Item("loan_reset", title, 1, f"/loan?edit={lo.id}#edit-loan", "warn", detail))
    return out


def wibor_error(conn: sqlite3.Connection, ctx: Context, memo: BalanceMemo) -> list[Item]:
    """Odczyt notowań WIBOR nie działa od kilku dni (M9 E4): prognoza raty jest nieaktualna."""
    err = wibor.error(conn)
    if err is None or (ctx.now - err[1]).days < wibor.ERROR_ALERT_DAYS:
        return []
    detail = f"Od {err[1]:%d.%m}: {err[0]}. Prognoza raty kredytu korzysta ze starych notowań."
    return [Item("wibor_error", "Nie mogę odczytać WIBOR 3M", 1, "/loan", "warn", detail)]


Provider = Callable[[sqlite3.Connection, Context, BalanceMemo], list[Item]]
PROVIDERS: tuple[Provider, ...] = (
    operational,
    uncategorized,
    new_series,
    series_changes,
    card_payments,
    card_due,
    forecast_low,
    piggy_transfer,
    savings_promo,
    promo_cards,
    loan_rate,
    loan_reset,
    wibor_error,
)
SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}


def items(
    snap: Snapshot, now: datetime, memo: BalanceMemo, forecast: Forecast | None = None
) -> list[Item]:
    """Wszystkie bieżące karty, także ręcznie ukryte (te odfiltrowuje `visible`)."""
    ctx = Context(now, snap, forecast)
    out = [item for provider in PROVIDERS for item in provider(snap.conn, ctx, memo)]
    return sorted(out, key=lambda i: SEVERITY_ORDER[i.severity])


def _dismissed(conn: sqlite3.Connection) -> set[str]:
    return set(db.kv_get(conn, DISMISSED_KEY) or [])


def _deleted(conn: sqlite3.Connection) -> set[str]:
    return set(db.kv_get(conn, DELETED_KEY) or [])


def visible(conn: sqlite3.Connection, every: list[Item]) -> list[Item]:
    hidden = _dismissed(conn) | _deleted(conn)
    return [i for i in every if i.key not in hidden]


def not_deleted(conn: sqlite3.Connection, every: list[Item]) -> list[Item]:
    gone = _deleted(conn)
    return [i for i in every if i.key not in gone]


def delete(conn: sqlite3.Connection, key: str) -> None:
    """Usuwa kartę na stałe: klucz (rodzaj + tytuł) zostaje na liście także po zniknięciu karty,
    więc karta o stałym tytule nie wróci, a zmiana tytułu to nowa karta."""
    db.kv_set(conn, DELETED_KEY, sorted(_deleted(conn) | {key}))


def dismiss(conn: sqlite3.Connection, key: str, current: list[Item]) -> None:
    """Ukrywa kartę; z listy wypadają klucze kart, których już nie ma."""
    keep = _dismissed(conn) & {i.key for i in current}
    db.kv_set(conn, DISMISSED_KEY, sorted(keep | {key}))


def restore(conn: sqlite3.Connection) -> None:
    db.kv_set(conn, DISMISSED_KEY, None)
