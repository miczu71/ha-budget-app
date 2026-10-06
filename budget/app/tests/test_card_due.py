"""Spłata karty kredytowej (M15 E4): zostało do spłaty z zamkniętego cyklu, termin, limit."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

import pytest

from budget import card, ha_publisher, inbox, summary
from budget.service import Service
from budget.snapshot import Snapshot
from budget.storage.db import now_iso

from .test_card import CARD, WAW, buy
from .test_categorize_engine import conn
from .test_forecast import snapshot
from .test_web import _client, service

__all__ = ["conn", "service"]


def debt(c: sqlite3.Connection, itbd: str, itav: str | None = None) -> None:
    at = "2026-10-12T10:00:00+00:00"
    snapshot(c, CARD, "ITBD", itbd, at)
    if itav is not None:
        snapshot(c, CARD, "ITAV", itav, at)


def test_none_without_card_balance(conn: sqlite3.Connection) -> None:
    assert card.due_status(conn, date(2026, 10, 12)) is None


def test_new_cycle_debits_are_not_due(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-09-20", amount="-300.00")  # poprzedni cykl — w ITBD i w wyciągu
    buy(conn, "2026-10-05", amount="-40.00")
    buy(conn, "2026-10-08", kind="fee", amount="-2.99")
    debt(conn, "342.99", "9657.01")
    cd = card.due_status(conn, date(2026, 10, 12))
    assert cd is not None
    assert cd.left == Decimal("300.00") and cd.due == date(2026, 10, 20) and cd.days_left == 8
    assert cd.debt == Decimal("342.99") and cd.available == Decimal("9657.01")
    assert not cd.overdue and cd.limit is None and cd.utilization is None


def test_repayment_after_close_counts_by_itself(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-10-05", amount="-40.00")
    buy(conn, "2026-10-06", kind="card_repayment", amount="250.00")
    debt(conn, "90.00")  # wyciąg 300 − spłata 250 + 40 nowych
    cd = card.due_status(conn, date(2026, 10, 12))
    assert cd is not None and cd.left == Decimal("50.00")


def test_cycle_boundary_counts_toward_statement(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-10-02", amount="-60.00")  # zakup z 30.09, zaksięgowany 2.10
    buy(conn, "2026-10-03", amount="-10.00")
    debt(conn, "370.00")
    cd = card.due_status(conn, date(2026, 10, 12))
    assert cd is not None and cd.left == Decimal("360.00")


def test_paid_off_and_overdue(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-10-05", amount="-40.00")
    debt(conn, "40.00")
    paid = card.due_status(conn, date(2026, 10, 25))
    assert paid is not None and paid.left == 0 and not paid.overdue
    snapshot(conn, CARD, "ITBD", "100.00", "2026-10-25T10:00:00+00:00")  # liczy się najnowsza
    late = card.due_status(conn, date(2026, 10, 25))
    assert late is not None and late.left == Decimal("60.00") and late.overdue


def test_authorization_only_in_itbd_raises_amount(conn: sqlite3.Connection) -> None:
    debt(conn, "125.00")  # zakup z wczoraj jeszcze bez księgowania
    cd = card.due_status(conn, date(2026, 10, 12))
    assert cd is not None and cd.left == Decimal("125.00")


def test_limit(conn: sqlite3.Connection) -> None:
    debt(conn, "2500.00")
    card.set_limit(conn, "10 000,00")
    cd = card.due_status(conn, date(2026, 10, 12))
    assert cd is not None and cd.limit == Decimal("10000.00") and cd.utilization == 0.25
    card.set_limit(conn, "")
    assert card.get_limit(conn) is None
    for bad in ("abc", "0", "-5"):
        with pytest.raises(card.CardError):
            card.set_limit(conn, bad)


def due_msgs(c: sqlite3.Connection, day: int) -> list[summary.Message]:
    now = datetime(2026, 10, day, 7, 30, tzinfo=WAW)
    return [m for m in summary.due(Snapshot(c), now) if m.kind == summary.CARD_DUE]


def due_items(c: sqlite3.Connection, day: int) -> list[inbox.Item]:
    now = datetime(2026, 10, day, 12, tzinfo=WAW)
    return [i for i in inbox.items(Snapshot(c), now, inbox.BalanceMemo()) if i.kind == "card_due"]


def test_reminder_on_15th_and_19th_once(conn: sqlite3.Connection) -> None:
    debt(conn, "1234.50")
    assert due_msgs(conn, 14) == []
    (msg,) = due_msgs(conn, 15)
    assert msg.title == "Karta kredytowa — spłata do 20.10"
    assert "1\u202f234,50\xa0zł" in msg.text and "wrzesień" in msg.text and "za 5 dni" in msg.text
    summary.mark_sent(conn, msg)
    assert due_msgs(conn, 15) == []
    (msg,) = due_msgs(conn, 19)
    assert "jutro" in msg.text and msg.period == "2026-10-1"


def test_no_reminder_when_paid(conn: sqlite3.Connection) -> None:
    debt(conn, "0.00")
    assert due_msgs(conn, 15) == [] and due_items(conn, 15) == []


def test_inbox_severity(conn: sqlite3.Connection) -> None:
    debt(conn, "300.00")
    (early,) = due_items(conn, 3)
    assert early.severity == "info" and "300,00\xa0zł" in early.title and early.link == "/card"
    assert due_items(conn, 15)[0].severity == "warn"
    (late,) = due_items(conn, 21)
    assert late.severity == "warn" and "po terminie" in late.title


def test_entity(conn: sqlite3.Connection) -> None:
    assert [e.key for e in ha_publisher.card_entities(Snapshot(conn), date(2026, 10, 12))] == [
        "card_purchases_month"
    ]
    debt(conn, "2500.00", "7500.00")
    card.set_limit(conn, "10000")
    _, e = ha_publisher.card_entities(Snapshot(conn), date(2026, 10, 12))
    assert e.key == "card_due" and e.state == "2500.00"
    assert e.config["unit_of_measurement"] == "PLN"
    assert e.attributes == {
        "due_date": "2026-10-20",
        "days_left": 8,
        "overdue": False,
        "debt": "2500.00",
        "available_bank": "7500.00",
        "limit": "10000.00",
        "utilization": 25.0,
    }


async def test_card_screen_and_limit(service: Service, monkeypatch: pytest.MonkeyPatch) -> None:
    c = service.conn
    c.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (2, 'card', 'PLN', ?)",
        (now_iso(),),
    )
    monkeypatch.setattr(service, "now", lambda: datetime(2026, 10, 16, 12, 0, tzinfo=WAW))
    async with _client(service) as client:
        bare = (await client.get("/card")).text
        debt(c, "300.00", "700.00")
        page = (await client.get("/card")).text
        bad = await client.post("/card/limit", data={"limit": "abc"})
        await client.post("/card/limit", data={"limit": "1000"})
        limited = (await client.get("/card")).text
        home = (await client.get("/")).text
    assert "Spłata" not in bare
    assert "Spłata — do 20.10" in page and "za 4 dni" in page and "due-verdict soon" in page
    assert "wpisz go" in page and "Wykorzystanie" not in page
    assert bad.status_code in (302, 303) and card.get_limit(c) == Decimal("1000.00")
    assert "Wykorzystanie" in limited and "30%" in limited and "width: 30%" in limited
    assert "Do spłaty" in home and "do 20.10" in home and "warn-text" in home
