"""Podsumowania na telefon i kalendarz płatności (M6)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from budget import calendar_ics, flex, summary
from budget.categorize import engine
from budget.service import Service
from budget.settings import Settings
from budget.snapshot import Snapshot

from .test_categorize_engine import add, conn
from .test_flex import serie, spend
from .test_web import _client, service

__all__ = ["conn", "service"]

WAW = ZoneInfo("Europe/Warsaw")
NBSP = " "


def snap(c: sqlite3.Connection) -> Snapshot:
    engine.recategorize(c)
    return Snapshot(c)


def test_zl_rounds_to_whole_zloty() -> None:
    assert summary.zl(Decimal("1234.5")) == f"1{NBSP}235{NBSP}zł"
    assert summary.zl(Decimal("-0.4")) == f"0{NBSP}zł"
    assert summary.zl(Decimal("-12")) == f"−12{NBSP}zł"


def test_weekly_pool_pace_week_upcoming_and_queue(conn: sqlite3.Connection) -> None:
    flex.set_budget(conn, date(2026, 10, 1), Decimal("3100"))  # 100 zł na dzień
    add(conn, "-200.00", "card", "LIDL XYZ POL", day="2026-10-02")  # przed minionym tygodniem
    add(conn, "-300.00", "card", "LIDL XYZ POL", day="2026-10-06")  # miniony tydzień
    add(conn, "-50.00", "card", "SKLEP ABC XYZ", day="2026-10-07")  # bez kategorii
    add(conn, "-999.00", "card", "LIDL XYZ POL", day="2026-10-12")  # dziś — poza tygodniem
    serie(conn, "media", "400.00")  # termin 7.10, niezapłacony — nadal oczekiwany (okno 5 dni)
    spend(conn, "400.00", "2026-09", "media")
    msg = summary.weekly(snap(conn), date(2026, 10, 12))  # poniedziałek

    assert msg.kind == summary.WEEKLY and msg.period == "2026-10-12"
    assert msg.title == "Budżet — tydzień 05.10–11.10"
    lines = msg.text.splitlines()
    # wydane 200 + 300 + 50 + 999 = 1549; tempo do wczoraj: 11 dni × 100 = 1100
    assert lines[0].startswith(f"Zostało 1{NBSP}551{NBSP}zł z 3{NBSP}100{NBSP}zł")
    assert lines[1] == f"Tempo: 449{NBSP}zł ponad plan"
    assert lines[2] == f"Tydzień: Jedzenie 300{NBSP}zł, Bez kategorii 50{NBSP}zł"
    assert lines[3] == f"W 7 dni zejdzie 400{NBSP}zł: Seria media 400{NBSP}zł"
    assert lines[4] == "Do przejrzenia: 1"


def test_weekly_without_pool_and_payments(conn: sqlite3.Connection) -> None:
    msg = summary.weekly(snap(conn), date(2026, 10, 12))
    assert msg.text.splitlines() == [
        f"Wydane elastyczne: 0{NBSP}zł (pula nieustawiona)",
        "Tydzień: brak wydatków elastycznych",
        "W 7 dni: brak płatności cyklicznych",
        "Do przejrzenia: 0",
    ]


def test_upcoming_spans_month_end_and_skips_paid(conn: sqlite3.Connection) -> None:
    serie(conn, "media", "400.00")  # termin 7. każdego miesiąca
    spend(conn, "400.00", "2026-10", "media")  # październik zapłacony
    assert summary.upcoming(snap(conn), date(2026, 10, 31)) == []  # 7.11 poza oknem 7 dni
    rows = summary.upcoming(snap(conn), date(2026, 11, 1))
    assert [d.due for d in rows] == [date(2026, 11, 7)]


def test_monthly_closes_previous_month(conn: sqlite3.Connection) -> None:
    flex.set_budget(conn, date(2026, 9, 1), Decimal("500"))
    add(conn, "-600.00", "card", "LIDL XYZ POL", day="2026-09-03")
    add(conn, "-40.00", "card", "SKLEP ABC XYZ", day="2026-09-04")
    msg = summary.monthly(snap(conn), date(2026, 10, 1))
    assert (msg.kind, msg.period, msg.title) == (
        summary.MONTHLY,
        "2026-09",
        "Budżet — wrzesień 2026",
    )
    assert msg.text.splitlines() == [
        f"Wydane 640{NBSP}zł z 500{NBSP}zł — ponad pulę o 140{NBSP}zł",
        f"Najwięcej: Jedzenie 600{NBSP}zł, Bez kategorii 40{NBSP}zł",
        "Do przejrzenia: 1",
    ]


@pytest.mark.parametrize(
    ("now", "kinds"),
    [
        (datetime(2026, 10, 12, 6, 59, tzinfo=WAW), []),  # poniedziałek przed 7:00
        (datetime(2026, 10, 12, 7, 0, tzinfo=WAW), ["weekly"]),
        (datetime(2026, 10, 12, 22, 0, tzinfo=WAW), ["weekly"]),  # zaległe z dzisiaj
        (datetime(2026, 10, 13, 7, 0, tzinfo=WAW), []),  # wtorek
        (datetime(2026, 10, 1, 7, 30, tzinfo=WAW), ["monthly"]),  # czwartek 1.
        (datetime(2027, 2, 1, 7, 0, tzinfo=WAW), ["monthly", "weekly"]),  # poniedziałek 1.
    ],
)
def test_due(conn: sqlite3.Connection, now: datetime, kinds: list[str]) -> None:
    assert [m.kind for m in summary.due(snap(conn), now)] == kinds


def test_sent_is_not_repeated(conn: sqlite3.Connection) -> None:
    s = snap(conn)
    now = datetime(2027, 2, 1, 7, 0, tzinfo=WAW)
    for msg in summary.due(s, now):
        summary.mark_sent(conn, msg)
    assert summary.due(s, now) == []
    assert summary.due(s, datetime(2027, 2, 8, 7, 0, tzinfo=WAW))[0].period == "2027-02-08"


def test_next_send() -> None:
    assert summary.next_send(datetime(2026, 10, 12, 6, 0, tzinfo=WAW)) == datetime(
        2026, 10, 12, 7, 0, tzinfo=WAW
    )
    assert summary.next_send(datetime(2026, 10, 12, 7, 0, tzinfo=WAW)) == datetime(
        2026, 10, 13, 7, 0, tzinfo=WAW
    )


# --- wysyłka -----------------------------------------------------------------------------------


class FakeHA:
    available = True

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str, Any]] = []

    async def notify(self, service: str, title: str, message: str, data: Any = None) -> None:
        self.sent.append((service, title, message, data))


def _with_target(service: Service, ha: FakeHA) -> Service:
    service.settings = Settings(
        **{**service.settings.model_dump(), "summary_notify_service": "notify.rodzina"}
    )
    service.ha = ha  # type: ignore[assignment]
    service.notifier.panel_url = "/app/x_budget"
    return service


async def test_send_due_summaries_marks_sent(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    ha = FakeHA()
    _with_target(service, ha)
    monkeypatch.setattr(service, "now", lambda: datetime(2026, 10, 12, 7, 0, 5, tzinfo=WAW))
    await service.send_due_summaries()
    await service.send_due_summaries()
    assert len(ha.sent) == 1
    target, title, _, data = ha.sent[0]
    assert target == "notify.rodzina" and title.startswith("Budżet — tydzień")
    assert data == {"clickAction": "/app/x_budget", "url": "/app/x_budget"}


async def test_no_target_no_send(service: Service, monkeypatch: pytest.MonkeyPatch) -> None:
    ha = FakeHA()
    service.ha = ha  # type: ignore[assignment]
    monkeypatch.setattr(service, "now", lambda: datetime(2026, 10, 12, 8, 0, tzinfo=WAW))
    await service.send_due_summaries()
    assert ha.sent == []


async def test_status_preview_and_send_now(service: Service) -> None:
    async with _client(service) as client:
        page = (await client.get("/status")).text
        assert "Podsumowania na telefon" in page and "summary_notify_service" in page
        r = await client.post("/summary/send", data={"kind": "weekly"})
        assert r.status_code == 303
        assert "Podsumowania wyłączone" in (await client.get("/status")).text
    ha = FakeHA()
    _with_target(service, ha)
    async with _client(service) as client:
        assert "notify.rodzina" in (await client.get("/status")).text
        await client.post("/summary/send", data={"kind": "monthly"})
        assert [s[1].startswith("Budżet — ") for s in ha.sent] == [True]


# --- kalendarz ---------------------------------------------------------------------------------


def test_calendar_events_status_and_format(conn: sqlite3.Connection) -> None:
    serie(conn, "media", "400.00")  # 7. każdego miesiąca
    spend(conn, "400.00", "2026-10", "media")
    body = calendar_ics.build(
        snap(conn), date(2026, 10, 12), datetime(2026, 10, 12, 1, 0, tzinfo=WAW)
    )
    assert body.startswith("BEGIN:VCALENDAR\r\n") and body.endswith("END:VCALENDAR\r\n")
    assert body.count("BEGIN:VEVENT") == 3  # 7.10 zapłacone, 7.11, 7.12 (≤ 60 dni)
    assert f"SUMMARY:Seria media −400{NBSP}zł (zapłacone)" in body
    assert "DTSTART;VALUE=DATE:20261207" in body
    assert "DTSTAMP:20261011T230000Z" in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))


def test_calendar_escape_and_fold() -> None:
    assert calendar_ics._escape("a,b;c\nd\\") == "a\\,b\\;c\\nd\\\\"
    folded = calendar_ics._fold("SUMMARY:" + "ż" * 60)
    parts = folded.split("\r\n ")
    assert len(parts) == 2 and all(len(p.encode()) <= 75 for p in parts)
    assert "".join(parts) == "SUMMARY:" + "ż" * 60


async def test_calendar_allowlist(service: Service) -> None:
    async with _client(service, peer=("172.30.32.1", 1)) as c:
        r = await c.get("/calendar.ics")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
        assert (await c.get("/status")).status_code == 403
    async with _client(service, peer=("172.30.33.9", 1)) as c:
        assert (await c.get("/calendar.ics")).status_code == 403


async def test_calendar_refresh_after_sync(service: Service) -> None:
    calls: list[str] = []

    class HA(FakeHA):
        async def update_entity(self, entity_id: str) -> None:
            calls.append(entity_id)

    service.ha = HA()  # type: ignore[assignment]
    await service.refresh_calendar()
    assert calls == []
    service.settings = Settings(
        **{**service.settings.model_dump(), "calendar_entity": "calendar.platnosci"}
    )
    await service.refresh_calendar()
    assert calls == ["calendar.platnosci"]


def test_settings_validate_new_options() -> None:
    s = Settings(summary_notify_service=" ", calendar_entity="")
    assert s.summary_notify_service is None and s.calendar_entity is None
    with pytest.raises(ValueError):
        Settings(summary_notify_service="mobile_app_x")
    with pytest.raises(ValueError):
        Settings(calendar_entity="sensor.x")
