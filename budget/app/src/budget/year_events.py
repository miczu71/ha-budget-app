"""Zdarzenia prognozy rocznej (M18 E2): zmiana kwoty serii, nowa seria i jednorazowa kwota.

Zdarzenie `plan` zmienia prognozę bazową, `scenario` tylko drugą projekcję („co jeśli”).
Propozycje (próg podatkowy, premia) liczone są na żywo z historii; wiersz w bazie powstaje dopiero
po zatwierdzeniu albo odrzuceniu i niesie `proposal_key`, więc ta sama propozycja nie wraca.
"""

from __future__ import annotations

import dataclasses
import sqlite3
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from budget import flex, forecast, money
from budget.recurring import schedule
from budget.recurring import series as S
from budget.snapshot import Snapshot
from budget.spending import add_months, month_start
from budget.storage import db

ZERO = money.ZERO
KINDS = {
    "series_amount": "Zmiana kwoty serii",
    "new_series": "Nowa seria",
    "one_off": "Jednorazowo",
}
MODES = {"plan": "Plan", "scenario": "Scenariusz"}
PIT_MIN_MONTHS = 3  # tyle miesięcy wypłaty w roku, żeby szukać spadku


class YearEventError(ValueError):
    """Komunikat dla użytkownika panelu."""


@dataclass(frozen=True)
class Event:
    id: int
    kind: str
    mode: str
    source: str
    name: str
    amount: Decimal  # series_amount/new_series: bezwzględna; one_off: ze znakiem
    start: date
    end: date | None
    series_id: int | None = None
    direction: str | None = None
    key: str | None = None


@dataclass(frozen=True)
class Proposal:
    key: str
    kind: str
    mode: str
    name: str
    amount: Decimal
    start: date
    end: date | None
    series_id: int | None = None
    why: str = ""


def _row(r: sqlite3.Row) -> Event:
    return Event(
        id=r["id"],
        kind=r["kind"],
        mode=r["mode"],
        source=r["source"],
        name=r["name"],
        amount=Decimal(r["amount"]),
        start=date.fromisoformat(r["month_from"]),
        end=date.fromisoformat(r["month_to"]) if r["month_to"] else None,
        series_id=r["series_id"],
        direction=r["direction"],
        key=r["proposal_key"],
    )


def active(conn: sqlite3.Connection) -> list[Event]:
    return [
        _row(r)
        for r in conn.execute("SELECT * FROM year_event WHERE status = 'active' ORDER BY id")
    ]


def get(conn: sqlite3.Connection, event_id: int) -> Event:
    row = conn.execute(
        "SELECT * FROM year_event WHERE id = ? AND status = 'active'", (event_id,)
    ).fetchone()
    if row is None:
        raise YearEventError("Nie ma takiego zdarzenia.")
    return _row(row)


def _validated(
    conn: sqlite3.Connection,
    kind: str,
    mode: str,
    name: str,
    amount: Decimal,
    start: date,
    end: date | None,
    series_id: int | None,
    direction: str | None,
) -> tuple[str, Decimal, date, date | None, int | None, str | None]:
    if kind not in KINDS or mode not in MODES:
        raise YearEventError("Nieznany rodzaj albo tryb zdarzenia.")
    name = name.strip()
    if not name:
        raise YearEventError("Podaj nazwę zdarzenia.")
    start = month_start(start)
    end = month_start(end) if end else None
    if kind == "one_off":
        end, series_id, direction = start, None, None
        if amount == 0:
            raise YearEventError("Kwota nie może być zerem.")
    else:
        if amount <= 0:
            raise YearEventError("Kwota musi być dodatnia.")
        if end and end < start:
            raise YearEventError("Koniec zdarzenia jest przed początkiem.")
    if kind == "series_amount":
        direction = None
        if series_id is None or not any(s.id == series_id for s in S.all_series(conn, ("active",))):
            raise YearEventError("Wybierz aktywną serię.")
    elif kind == "new_series":
        series_id = None
        if direction not in ("in", "out"):
            raise YearEventError("Wybierz kierunek: wpływ albo wydatek.")
    return name, amount, start, end, series_id, direction


def add(
    conn: sqlite3.Connection,
    *,
    kind: str,
    mode: str,
    name: str,
    amount: Decimal,
    start: date,
    end: date | None = None,
    series_id: int | None = None,
    direction: str | None = None,
    source: str = "manual",
    status: str = "active",
    key: str | None = None,
) -> int:
    name, amount, start, end, series_id, direction = _validated(
        conn, kind, mode, name, amount, start, end, series_id, direction
    )
    cur = conn.execute(
        "INSERT INTO year_event (kind, mode, source, status, name, series_id, direction, amount, "
        "month_from, month_to, proposal_key, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            kind,
            mode,
            source,
            status,
            name,
            series_id,
            direction,
            money.fmt(amount),
            start.isoformat(),
            end.isoformat() if end else None,
            key,
            db.now_iso(),
        ),
    )
    return int(cur.lastrowid or 0)


def update(
    conn: sqlite3.Connection,
    event_id: int,
    *,
    mode: str,
    name: str,
    amount: Decimal,
    start: date,
    end: date | None,
    series_id: int | None = None,
    direction: str | None = None,
) -> None:
    """Zmienia zdarzenie (rodzaj zostaje); przy zatwierdzonej propozycji zostaje jej klucz."""
    old = get(conn, event_id)
    name, amount, start, end, series_id, direction = _validated(
        conn, old.kind, mode, name, amount, start, end, series_id, direction
    )
    conn.execute(
        "UPDATE year_event SET mode = ?, name = ?, series_id = ?, direction = ?, amount = ?, "
        "month_from = ?, month_to = ? WHERE id = ?",
        (
            mode,
            name,
            series_id,
            direction,
            money.fmt(amount),
            start.isoformat(),
            end.isoformat() if end else None,
            event_id,
        ),
    )


def _month(text: str) -> date | None:
    try:
        return date.fromisoformat(f"{text.strip()}-01") if text.strip() else None
    except ValueError:
        raise YearEventError("Podaj miesiąc w formacie RRRR-MM.") from None


def save_form(conn: sqlite3.Connection, event_id: int | None, form: Mapping[str, str]) -> None:
    """Dodaje (`event_id` None) albo zmienia zdarzenie z pól formularza. Kwotę wpisuje się
    dodatnią; kierunek (wpływ/wydatek) nadaje znak zdarzeniu jednorazowemu i kierunek nowej serii.
    Przy zmianie rodzaj zostaje taki, jak w zapisanym zdarzeniu."""

    def text(name: str) -> str:
        return str(form.get(name, "")).strip()

    try:
        value = money.parse(text("amount"))
    except money.AmountError:
        value = None
    if value is None or value <= 0:
        raise YearEventError("Podaj kwotę większą od zera, np. 2500 albo 2 500,00.")
    first = _month(text("start"))
    if first is None:
        raise YearEventError("Podaj miesiąc początku.")
    kind = text("kind") if event_id is None else get(conn, event_id).kind
    direction = text("direction") or None
    fields = {
        "mode": text("mode") or "plan",
        "name": text("name"),
        "amount": -value if kind == "one_off" and direction == "out" else value,
        "start": first,
        "end": _month(text("end")),
        "series_id": int(text("series_id")) if text("series_id").isdigit() else None,
        "direction": direction,
    }
    if event_id is None:
        add(conn, kind=kind, **fields)  # type: ignore[arg-type]
    else:
        update(conn, event_id, **fields)  # type: ignore[arg-type]


def delete(conn: sqlite3.Connection, event_id: int) -> None:
    """Usuwa zdarzenie ręczne; zatwierdzoną propozycję odrzuca (nie wróci)."""
    old = get(conn, event_id)
    if old.source == "proposed":
        conn.execute("UPDATE year_event SET status = 'dismissed' WHERE id = ?", (event_id,))
    else:
        conn.execute("DELETE FROM year_event WHERE id = ?", (event_id,))


def _seen_keys(conn: sqlite3.Connection) -> set[str]:
    return {
        r[0]
        for r in conn.execute("SELECT proposal_key FROM year_event WHERE proposal_key IS NOT NULL")
    }


def decide(conn: sqlite3.Connection, proposal: Proposal, approve: bool) -> None:
    """Zatwierdza (zdarzenie aktywne) albo odrzuca propozycję (ślad w bazie, żeby nie wróciła)."""
    add(
        conn,
        kind=proposal.kind,
        mode=proposal.mode,
        name=proposal.name,
        amount=proposal.amount,
        start=proposal.start,
        end=proposal.end,
        series_id=proposal.series_id,
        source="proposed",
        status="active" if approve else "dismissed",
        key=proposal.key,
    )


# --- zastosowanie do prognozy -------------------------------------------------------------------


def _covers(event: Event, month: date) -> bool:
    return event.start <= month and (event.end is None or month <= event.end)


def apply(
    events: Sequence[Event],
    dues: Mapping[date, Sequence[schedule.Due]],
    months: Sequence[date],
) -> tuple[dict[date, list[schedule.Due]], dict[date, Decimal]]:
    """Terminy serii z podmienionymi kwotami (`series_amount`) i dopłaty/wypłaty miesięczne
    (`new_series`, `one_off`) do `year.project`. Przy zachodzących na siebie zmianach kwoty tej
    samej serii wygrywa późniejsze zdarzenie."""
    out = {m: list(rows) for m, rows in dues.items()}
    extra: dict[date, Decimal] = {}
    for ev in events:
        for month in months:
            if not _covers(ev, month):
                continue
            if ev.kind == "series_amount":
                out[month] = [
                    dataclasses.replace(
                        d, series=dataclasses.replace(d.series, expected_amount=ev.amount)
                    )
                    if d.series.id == ev.series_id
                    else d
                    for d in out.get(month, ())
                ]
            elif ev.kind == "new_series":
                sign = 1 if ev.direction == "in" else -1
                extra[month] = extra.get(month, ZERO) + sign * ev.amount
            else:
                extra[month] = extra.get(month, ZERO) + ev.amount
    return out, extra


# --- propozycje z historii ----------------------------------------------------------------------


def horizon_end(today: date) -> date:
    """Koniec roku kalendarzowego; od 1.11 koniec roku następnego."""
    return date(today.year + (1 if today.month >= 11 else 0), 12, 31)


def _target_years(today: date) -> list[int]:
    """Lata, które prognoza obejmuje: bieżący i — od 1.11 — następny."""
    return list(range(today.year, horizon_end(today).year + 1))


def _in_horizon(start: date, end: date | None, today: date) -> bool:
    first = month_start(today)
    return start <= horizon_end(today) and (end is None or end >= first)


def _pit(snap: Snapshot, today: date) -> list[Proposal]:
    """Próg podatkowy: wypłata, która w poprzednim roku spadła o > `DROP_RATIO` względem
    pierwszego miesiąca roku, wraca w styczniu do wyższej kwoty i spada w tym samym miesiącu."""
    payday = forecast.payday_series_id(snap.conn)
    live = {s.id: s for s in S.all_series(snap.conn, ("active",))}
    series = live.get(payday) if payday is not None else None
    if series is None:
        return []
    by_month: dict[date, Decimal] = {}
    for t in snap.members().get(series.id, []):
        m = month_start(t.day)
        by_month[m] = by_month.get(m, ZERO) + t.amount
    out: list[Proposal] = []
    for year in _target_years(today):
        values = sorted((m, v) for m, v in by_month.items() if m.year == year - 1 and v > 0)
        limit = flex.bonus_limit([v for _, v in values])
        values = [(m, v) for m, v in values if limit is None or v <= limit]
        if len(values) < PIT_MIN_MONTHS:
            continue
        base = values[0][1]
        drop = next((m for m, v in values if v < base * (1 - flex.DROP_RATIO)), None)
        if drop is None:
            continue
        before = Decimal(statistics.median(v for m, v in values if m < drop)).quantize(money.CENT)
        after = Decimal(statistics.median(v for m, v in values if m >= drop)).quantize(money.CENT)
        drop_now = drop.replace(year=year)
        why = f"W {year - 1} wypłata spadła od {drop:%m.%Y} o {(1 - after / before):.0%}."
        if before != series.expected_amount:
            start, end = date(year, 1, 1), add_months(drop_now, -1)
            if _in_horizon(start, end, today):
                out.append(
                    Proposal(
                        f"pit:{series.id}:{year}:a",
                        "series_amount",
                        "plan",
                        f"Wypłata od stycznia {year}",
                        before,
                        start,
                        end,
                        series.id,
                        why,
                    )
                )
        if after != series.expected_amount:
            end = date(year, 12, 1)
            if _in_horizon(drop_now, end, today):
                out.append(
                    Proposal(
                        f"pit:{series.id}:{year}:b",
                        "series_amount",
                        "plan",
                        f"Wypłata po progu od {drop_now:%m.%Y}",
                        after,
                        drop_now,
                        end,
                        series.id,
                        why,
                    )
                )
    return out


def _bonus(snap: Snapshot, today: date) -> list[Proposal]:
    """Premia: miesiąc, w którym wpływ ze źródła przekroczył `flex.bonus_limit`, powtórzony
    w tym roku jako scenariusz (nadwyżka ponad typową wypłatę)."""
    out: list[Proposal] = []
    for year in _target_years(today):
        data = flex.income_by_source(snap.conn, date(year - 1, 1, 1), date(year, 1, 1))
        for name in sorted(data):
            values = {m: v for m, v in data[name].items() if v > 0}
            limit = flex.bonus_limit(list(values.values()))
            if limit is None:
                continue
            typical = [v for v in values.values() if v <= limit]
            if not typical:
                continue
            usual = Decimal(statistics.median(typical))
            for m, v in sorted(values.items()):
                if v <= limit:
                    continue
                at = m.replace(year=year)
                if not _in_horizon(at, at, today):
                    continue
                out.append(
                    Proposal(
                        f"bonus:{name}:{at:%Y-%m}",
                        "one_off",
                        "scenario",
                        f"Premia ({name})",
                        (v - usual).quantize(money.CENT),
                        at,
                        at,
                        None,
                        f"W {m:%m.%Y} wpływ był większy niż zwykle o {v - usual:.0f} zł.",
                    )
                )
    return out


def proposals(snap: Snapshot, today: date) -> list[Proposal]:
    """Propozycje, których użytkownik jeszcze nie zatwierdził ani nie odrzucił."""
    seen = _seen_keys(snap.conn)
    return [p for p in _pit(snap, today) + _bonus(snap, today) if p.key not in seen]
