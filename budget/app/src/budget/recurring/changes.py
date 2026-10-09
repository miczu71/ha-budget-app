"""Zmiany serii (M5b E3): inna kwota, spóźniona, ustała — karty dzwonka z decyzją użytkownika.

Zmiany są liczone na bieżąco z terminów (`schedule.history`) i przynależności transakcji
(`series.assign`); w bazie zapisuje się tylko decyzja (`series_ack`). Liczą się wyłącznie serie
aktywne.

- **Inna kwota** — ostatni zapłacony termin z bieżącego albo poprzedniego miesiąca ma kwotę
  poza `oczekiwana ± tolerancja`. „Przyjmij nową” zmienia oczekiwaną kwotę (karta znika, bo
  różnica jest zerowa), „jednorazowo” zapisuje decyzję dla tego terminu.
- **Spóźniona** — termin z bieżącego albo poprzedniego miesiąca bez płatności po oknie.
  „Pomiń ten okres” zapisuje decyzję; termin dostaje status „pominięte”.
- **Ustała** — dwa ostatnie minione terminy bez płatności (pominięty termin przerywa serię
  braków). Zastępuje kartę „spóźniona” tej serii. „Zostaw” ukrywa kartę do następnego braku.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from budget import money
from budget.recurring import schedule
from budget.recurring import series as S
from budget.recurring.schedule import Acks, Due
from budget.recurring.series import Candidate, Series, SeriesError
from budget.snapshot import Snapshot
from budget.spending import add_months, month_start
from budget.storage.db import now_iso

AMOUNT, LATE, STOPPED = "amount", "late", "stopped"
DECISIONS = {AMOUNT: "once", LATE: "skip", STOPPED: "keep"}
STOP_AFTER = 2  # tyle ostatnich minionych terminów bez płatności = seria ustała
_ABSENT = (schedule.LATE, schedule.MISSING)


@dataclass(frozen=True)
class Change:
    series: Series
    kind: str
    period: str  # RRRR-MM terminu, którego dotyczy zmiana
    detail: str
    amount: Decimal | None = None  # zapłacona kwota (dla „przyjmij nową”)


def _period(d: Due) -> str:
    assert d.due is not None
    return f"{d.due:%Y-%m}"


def _amount_change(s: Series, rows: Sequence[Due], acks: Acks, recent: date) -> Change | None:
    paid = [d for d in rows if d.status == schedule.PAID]
    if not paid:
        return None
    last = paid[-1]
    assert last.due is not None
    if last.due < recent:
        return None
    amount = last.paid_amount
    if abs(amount - s.expected_amount) <= s.tolerance:
        return None
    if acks.get((s.id, _period(last), AMOUNT)) == DECISIONS[AMOUNT]:
        return None
    detail = (
        f"termin {last.due:%Y-%m-%d}: zapłacono {money.fmt(amount)} "
        f"zamiast {money.fmt(s.expected_amount)}"
    )
    return Change(s, AMOUNT, _period(last), detail, amount)


def _elapsed(rows: Sequence[Due]) -> list[Due]:
    return [d for d in rows if d.status != schedule.EXPECTED]


def detect(
    series: Sequence[Series],
    members: Mapping[int, Sequence[Candidate]],
    acks: Acks,
    today: date,
    overrides: schedule.Overrides | None = None,
) -> list[Change]:
    """Zmiany aktywnych serii, na które użytkownik jeszcze nie zdecydował."""
    recent = add_months(month_start(today), -1)  # tylko bieżący i poprzedni miesiąc
    out: list[Change] = []
    for s in series:
        if s.status != "active":
            continue
        rows = schedule.history(s, members.get(s.id, []), today, acks, overrides)
        if not rows:
            continue
        if change := _amount_change(s, rows, acks, recent):
            out.append(change)
        elapsed = _elapsed(rows)
        tail = elapsed[-STOP_AFTER:]
        if len(tail) == STOP_AFTER and all(d.status in _ABSENT for d in tail):
            last = tail[-1]
            assert last.due is not None
            if acks.get((s.id, _period(last), STOPPED)) != DECISIONS[STOPPED]:
                detail = (
                    f"brak płatności w {STOP_AFTER} ostatnich terminach "
                    f"(ostatni: {last.due:%Y-%m-%d})"
                )
                out.append(Change(s, STOPPED, _period(last), detail))
            continue  # ustała zastępuje kartę „spóźniona”
        for d in rows:
            assert d.due is not None
            if d.status in _ABSENT and d.due >= recent:
                out.append(Change(s, LATE, _period(d), f"termin {d.due:%Y-%m-%d} bez płatności"))
    return out


def for_db(snap: Snapshot, today: date) -> list[Change]:
    active = S.all_series(snap.conn, ("active",))
    if not active:
        return []
    members = S.assign(active, snap.candidates())
    acks, overrides = schedule.acks_from_db(snap.conn), schedule.overrides_from_db(snap.conn)
    return detect(active, members, acks, today, overrides)


def ack(conn: sqlite3.Connection, series_id: int, period: str, kind: str) -> None:
    """Zapisuje decyzję „jednorazowo” / „pomiń” / „zostaw” dla terminu serii."""
    if kind not in DECISIONS:
        raise SeriesError("Nieznany rodzaj zmiany.")
    S.get(conn, series_id)
    try:
        date.fromisoformat(f"{period}-01")
    except ValueError as exc:
        raise SeriesError("Zły okres.") from exc
    conn.execute(
        "INSERT OR REPLACE INTO series_ack (series_id, period, kind, decision, decided_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (series_id, period, kind, DECISIONS[kind], now_iso()),
    )


def accept_amount(conn: sqlite3.Connection, series_id: int, amount: Decimal) -> None:
    """„Przyjmij nową”: oczekiwana kwota serii := zapłacona kwota."""
    s = S.get(conn, series_id)
    if s.status != "active":
        raise SeriesError(f"Seria „{s.name}” nie jest aktywna.")
    if amount <= 0:
        raise SeriesError("Kwota musi być większa od zera.")
    conn.execute(
        "UPDATE series SET expected_amount = ? WHERE id = ?",
        (money.fmt(amount.quantize(money.CENT)), series_id),
    )
