"""Kalendarz płatności (M6): terminy aktywnych serii jako ICS dla integracji HA Remote Calendar.

Wydarzenia całodniowe od początku bieżącego miesiąca do `DAYS` dni naprzód — także terminy już
zapłacone, z dopiskiem statusu. Kwota: zapłacona, a bez płatności — oczekiwana kwota serii.
Terminy z `schedule.for_month`, więc kalendarz zgadza się z ekranem Cykliczne.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from budget.recurring import schedule
from budget.snapshot import Snapshot
from budget.spending import add_months, month_start
from budget.summary import zl

DAYS = 60
STATUS = {
    schedule.PAID: "zapłacone",
    schedule.LATE: "spóźnione",
    schedule.MISSING: "brak płatności",
    schedule.SKIPPED: "pominięte",
}
CADENCE = {"M": "co miesiąc", "Q": "co kwartał", "Y": "co rok"}


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: linie do 75 oktetów, kontynuacja od spacji (bez dzielenia znaków UTF-8)."""
    out: list[str] = []
    cur = ""
    for ch in line:
        if len((cur + ch).encode()) > (75 if not out else 74):
            out.append(cur)
            cur = ""
        cur += ch
    out.append(cur)
    return "\r\n ".join(out)


def dues(snap: Snapshot, today: date, days: int = DAYS) -> list[schedule.Due]:
    end = today + timedelta(days=days)
    rows: list[schedule.Due] = []
    month = month_start(today)
    while month <= end:
        rows += [
            d
            for d in schedule.for_month(snap, month, today).rows
            if d.due is not None and d.due <= end
        ]
        month = add_months(month, 1)
    return rows


def build(snap: Snapshot, today: date, now: datetime) -> str:
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ha-budget-app//Budzet Domowy//PL",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Płatności",
    ]
    for d in dues(snap, today):
        assert d.due is not None
        s = d.series
        amount = d.paid_amount if d.txns else s.expected_amount
        sign = "−" if s.direction == "out" else "+"
        title = f"{s.name} {sign}{zl(amount)}"
        if d.status in STATUS:
            done = "wpłynęło" if s.direction == "in" and d.status == schedule.PAID else None
            title += f" ({done or STATUS[d.status]})"
        lines += [
            "BEGIN:VEVENT",
            f"UID:budget-{s.id}-{d.due:%Y%m%d}@ha-budget-app",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{d.due:%Y%m%d}",
            f"DTEND;VALUE=DATE:{d.due + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(title)}",
            f"DESCRIPTION:{_escape(CADENCE.get(s.cadence, s.cadence))}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "".join(_fold(line) + "\r\n" for line in lines)
