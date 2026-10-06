"""Podsumowania na telefon (M6): tydzień w poniedziałek, zamknięcie miesiąca 1. dnia.

Cel: korekta wydatków w trakcie miesiąca — ile zostało z puli Flex i jak idzie tempo, na co
poszło w minionym tygodniu, co zejdzie z konta w najbliższych 7 dniach, ile czeka na przejrzenie.
Liczby z tych samych funkcji co panel (`flex.build`, `spending.sums`, `schedule.for_month`).
Kwoty w pełnych złotych — to wiadomość na telefon, nie wyciąg.

Wysyłka o `SEND_AT`; podsumowanie, które nie wyszło (add-on nie działał), wychodzi po starcie
tego samego dnia. Wysłane okresy w `kv` (`SENT_KEY`) — bez dubli po restarcie.
Tą samą drogą idzie przypomnienie o płatnościach kartą kredytową (M15, `card.REMIND_DAYS`)
i o spłacie karty przed terminem (M15 E4, `card.DUE_REMIND_DAYS`) — ta kwota z groszami.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from budget import card, flex, review
from budget.categorize import taxonomy
from budget.recurring import schedule
from budget.snapshot import Snapshot
from budget.spending import add_months, month_start, sums
from budget.storage.db import kv_get, kv_set

SEND_AT = time(7, 0)
SENT_KEY = "summary_sent"
WEEKLY, MONTHLY, CARD, CARD_DUE = "weekly", "monthly", "card", "card_due"
UPCOMING_DAYS = 7
TOP = 3
MONTH_NAMES = (
    "styczeń",
    "luty",
    "marzec",
    "kwiecień",
    "maj",
    "czerwiec",
    "lipiec",
    "sierpień",
    "wrzesień",
    "październik",
    "listopad",
    "grudzień",
)


@dataclass(frozen=True)
class Message:
    kind: str  # WEEKLY | MONTHLY | CARD | CARD_DUE
    period: str  # znacznik wysłanego okresu: dzień poniedziałku, RRRR-MM albo RRRR-MM-<dni>
    title: str
    text: str


def zl(amount: Decimal) -> str:
    """`1234.56` → `1 235 zł` (twarda spacja w grupach i przed walutą)."""
    whole = int(abs(amount).quantize(Decimal(1), ROUND_HALF_UP))
    sign = "−" if amount < 0 and whole else ""
    return f"{sign}{whole:,}".replace(",", " ") + " zł"


def zl_gr(amount: Decimal) -> str:
    """`1234.5` → `1 234,50 zł` — kwota do przelewu, bez zaokrąglania (spacje jak w `zl`)."""
    return f"{amount:,.2f}".replace(",", "\xa0").replace(".", ",") + "\xa0zł"


def _short(d: date) -> str:
    return f"{d:%d.%m}"


def top_categories(
    snap: Snapshot, start: date, end: date, n: int = TOP
) -> list[tuple[str, Decimal]]:
    """Wydatki elastyczne netto okresu [start, end) po kategorii głównej, z „Bez kategorii”;
    jak „wydane” w budżecie Flex (serie liczone w puli pominięte)."""
    conn = snap.conn
    s = sums(conn, start, end, flex.pool_series(snap).skip)
    mains = {m.category.id: m.category.name for m in taxonomy.tree(conn)}
    by_main: dict[str, Decimal] = defaultdict(Decimal)
    for leaf in taxonomy.leaves(conn).values():
        acc = s.by_leaf.get(leaf.id)
        if acc is not None and leaf.flex_group == "flexible":
            by_main[mains.get(leaf.parent_id or 0, leaf.name)] -= acc.amount
    if s.unc_out.amount:
        by_main["Bez kategorii"] += s.unc_out.amount
    ranked = sorted(((k, v) for k, v in by_main.items() if v > 0), key=lambda kv: -kv[1])
    return ranked[:n]


def _top_line(label: str, top: list[tuple[str, Decimal]]) -> str:
    if not top:
        return f"{label}: brak wydatków elastycznych"
    return f"{label}: " + ", ".join(f"{name} {zl(v)}" for name, v in top)


def upcoming(snap: Snapshot, today: date, days: int = UPCOMING_DAYS) -> list[schedule.Due]:
    """Terminy wydatkowych serii do `today + days` (bez dzisiejszego +days), jeszcze
    niezapłacone — także spóźnione; od największej kwoty."""
    end = today + timedelta(days=days)
    months = {month_start(today), month_start(end - timedelta(days=1))}
    rows = [
        d
        for m in sorted(months)
        for d in schedule.for_month(snap, m, today).rows
        if d.series.direction == "out"
        and d.status in (schedule.EXPECTED, schedule.LATE)
        and d.due is not None
        and d.due < end
    ]
    return sorted(rows, key=lambda d: -d.series.expected_amount)


def _pool_lines(fm: flex.FlexMonth, today: date) -> list[str]:
    if fm.budget is None or fm.remaining is None:
        return [f"Wydane elastyczne: {zl(fm.spent)} (pula nieustawiona)"]
    lines = [f"Zostało {zl(fm.remaining)} z {zl(fm.budget)}"]
    if fm.per_day is not None:
        lines[0] += f" · {zl(fm.per_day)}/dzień"
    # Tempo do wczoraj: o 7:00 dzisiejsze wydatki dopiero się zaczynają
    expected = fm.budget * (today.day - 1) / fm.days_in_month
    diff = fm.spent - expected
    if abs(diff) < 1:
        lines.append("Tempo: zgodnie z planem")
    elif diff > 0:
        lines.append(f"Tempo: {zl(diff)} ponad plan")
    else:
        lines.append(f"Tempo: {zl(-diff)} poniżej planu")
    return lines


def weekly(snap: Snapshot, today: date) -> Message:
    """Podsumowanie minionego tygodnia (pon–nd przed `today`) i stan bieżącego miesiąca."""
    monday = today - timedelta(days=today.weekday())
    start, end = monday - timedelta(days=7), monday
    fm = flex.build(snap, month_start(today), today)
    lines = _pool_lines(fm, today)
    lines.append(_top_line("Tydzień", top_categories(snap, start, end)))
    due = upcoming(snap, today)
    if due:
        total = sum((d.series.expected_amount for d in due), Decimal(0))
        names = ", ".join(f"{d.series.name} {zl(d.series.expected_amount)}" for d in due[:TOP])
        more = f" i {len(due) - TOP} więcej" if len(due) > TOP else ""
        lines.append(f"W {UPCOMING_DAYS} dni zejdzie {zl(total)}: {names}{more}")
    else:
        lines.append(f"W {UPCOMING_DAYS} dni: brak płatności cyklicznych")
    lines.append(f"Do przejrzenia: {review.pending_count(snap.conn)}")
    title = f"Budżet — tydzień {_short(start)}–{_short(end - timedelta(days=1))}"
    return Message(WEEKLY, monday.isoformat(), title, "\n".join(lines))


def monthly(snap: Snapshot, today: date) -> Message:
    """Zamknięcie miesiąca poprzedzającego `today`."""
    month = add_months(month_start(today), -1)
    fm = flex.build(snap, month, today)
    name = f"{MONTH_NAMES[month.month - 1]} {month.year}"
    if fm.budget is None or fm.remaining is None:
        lines = [f"Wydane elastyczne: {zl(fm.spent)} (pula nieustawiona)"]
    elif fm.remaining >= 0:
        lines = [f"Wydane {zl(fm.spent)} z {zl(fm.budget)} — zostało {zl(fm.remaining)}"]
    else:
        lines = [f"Wydane {zl(fm.spent)} z {zl(fm.budget)} — ponad pulę o {zl(-fm.remaining)}"]
    lines.append(_top_line("Najwięcej", top_categories(snap, month, month_start(today))))
    lines.append(f"Do przejrzenia: {review.pending_count(snap.conn)}")
    return Message(MONTHLY, f"{month:%Y-%m}", f"Budżet — {name}", "\n".join(lines))


def card_reminder(cm: card.CardMonth, today: date) -> Message:
    """Przypomnienie o płatnościach kartą kredytową (M15; licznik wspólny albo per osoba)."""
    end = _short(cm.last_day)
    if cm.shared:
        title = f"Karta kredytowa — {cm.count}/{cm.threshold}"
        lines = [
            f"Brakuje {cm.missing} z {cm.threshold} płatności kartą — miesiąc kończy się {end}, "
            "bez nich bank pobierze opłatę za kartę.",
            "BLIK się nie liczy; bank liczy kartę główną i dodatkową osobno.",
        ]
    else:
        title = "Karta kredytowa — " + (
            "brakuje płatności" if cm.missing else "płatności do przypisania"
        )
        lines = [
            " · ".join(
                f"{h.name}: {h.count}/{h.threshold}"
                + (f" (brakuje {h.missing})" if h.missing else "")
                for h in cm.holders
            )
        ]
        if cm.unassigned:
            lines.append(
                f"Do przypisania: {cm.unassigned} — nieprzypisana płatność nie liczy się nikomu."
            )
        lines.append(
            f"Miesiąc kończy się {end}; bez {cm.threshold} płatności bank pobierze opłatę za kartę "
            "tej osoby. BLIK się nie liczy."
        )
    period = f"{cm.month:%Y-%m}-{card.days_to_end(today)}"
    return Message(CARD, period, title, "\n".join(lines))


def when(days: int) -> str:
    return {0: "dziś", 1: "jutro"}.get(days, f"za {days} dni")


def due_reminder(cd: card.CardDue) -> Message:
    """Przypomnienie o spłacie karty z zamkniętego cyklu przed terminem (M15 E4)."""
    cycle = MONTH_NAMES[add_months(cd.due, -1).month - 1]
    return Message(
        CARD_DUE,
        f"{cd.due:%Y-%m}-{cd.days_left}",
        f"Karta kredytowa — spłata do {_short(cd.due)}",
        f"Zostało {zl_gr(cd.left)} z cyklu: {cycle}; termin {when(cd.days_left)}. "
        "Po terminie bank nalicza odsetki.",
    )


def build(snap: Snapshot, kind: str, today: date) -> Message:
    return weekly(snap, today) if kind == WEEKLY else monthly(snap, today)


def due(snap: Snapshot, now: datetime) -> list[Message]:
    """Podsumowania do wysłania teraz: dziś termin, po `SEND_AT`, jeszcze nie wysłane."""
    if now.time() < SEND_AT:
        return []
    today = now.date()
    sent = kv_get(snap.conn, SENT_KEY) or {}
    out = []
    if today.day == 1 and sent.get(MONTHLY) != f"{add_months(today, -1):%Y-%m}":
        out.append(monthly(snap, today))
    if today.weekday() == 0 and sent.get(WEEKLY) != today.isoformat():
        out.append(weekly(snap, today))
    cm = card.month_status(snap.conn, today) if card.remind_today(today) else None
    if cm and cm.needs_action:
        msg = card_reminder(cm, today)
        if sent.get(CARD) != msg.period:
            out.append(msg)
    cd = card.due_status(snap.conn, today) if card.due_remind_today(today) else None
    if cd and cd.left:
        msg = due_reminder(cd)
        if sent.get(CARD_DUE) != msg.period:
            out.append(msg)
    return out


def mark_sent(conn: sqlite3.Connection, msg: Message) -> None:
    sent = kv_get(conn, SENT_KEY) or {}
    sent[msg.kind] = msg.period
    kv_set(conn, SENT_KEY, sent)


def next_send(now: datetime) -> datetime:
    """Najbliższa godzina `SEND_AT` po `now` (w strefie `now`)."""
    at = datetime.combine(now.date(), SEND_AT, tzinfo=now.tzinfo)
    return at if at > now else at + timedelta(days=1)
