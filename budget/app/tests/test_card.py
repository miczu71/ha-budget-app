"""Licznik płatności kartą kredytową (M15 E1): stan, przypomnienia, dzwonek, encja, kafelek."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from budget import card, ha_publisher, inbox, summary
from budget.service import Service
from budget.snapshot import Snapshot
from budget.storage.db import now_iso

from .test_categorize_engine import add, conn
from .test_web import _client, service

__all__ = ["conn", "service"]

WAW = ZoneInfo("Europe/Warsaw")
CARD = 2  # konto karty w fiksturze `conn`


def buy(
    c: sqlite3.Connection,
    day: str,
    n: int = 1,
    kind: str = "card",
    amount: str = "-10.00",
    account: int = CARD,
) -> None:
    for _ in range(n):
        add(c, amount, kind, "SKLEP ABC XYZ", day=day, account=account)


def card_msgs(c: sqlite3.Connection, now: datetime) -> list[summary.Message]:
    return [m for m in summary.due(Snapshot(c), now) if m.kind == summary.CARD]


def card_items(c: sqlite3.Connection, now: datetime) -> list[inbox.Item]:
    return [
        i for i in inbox.items(Snapshot(c), now, inbox.BalanceMemo()) if i.kind == "card_payments"
    ]


def test_counts_only_card_purchases_on_card_account(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-10-10", 3)
    buy(conn, "2026-10-11", kind="card_refund", amount="10.00")
    buy(conn, "2026-10-12", kind="card_repayment", amount="500.00")
    buy(conn, "2026-10-12", kind="fee", amount="-2.99")
    buy(conn, "2026-10-12", account=1)  # karta debetowa
    cm = card.month_status(conn, date(2026, 10, 20))
    assert cm is not None and cm.count == 3 and cm.missing == 2
    assert cm.month == date(2026, 10, 1) and cm.last_day == date(2026, 10, 31)


def test_month_edges_count_by_both_dates(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-10-01", 5)  # po dacie zakupu (−2 dni) to jeszcze wrzesień
    buy(conn, "2026-10-15", 2)
    assert card.month_status(conn, date(2026, 10, 20)).count == 2  # type: ignore[union-attr]
    assert card.month_status(conn, date(2026, 9, 20)).count == 0  # type: ignore[union-attr]


def test_no_card_account(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM account WHERE kind = 'card'")
    assert card.month_status(conn, date(2026, 10, 20)) is None


@pytest.mark.parametrize(
    ("now", "periods"),
    [
        (datetime(2026, 10, 25, 7, 0, tzinfo=WAW), []),  # 6 dni przed końcem
        (datetime(2026, 10, 26, 6, 59, tzinfo=WAW), []),  # przed 7:00
        (datetime(2026, 10, 26, 7, 0, tzinfo=WAW), ["2026-10-5"]),
        (datetime(2026, 10, 27, 7, 0, tzinfo=WAW), []),
        (datetime(2026, 10, 30, 21, 0, tzinfo=WAW), ["2026-10-1"]),  # zaległe z dzisiaj
        (datetime(2026, 10, 31, 7, 0, tzinfo=WAW), []),
    ],
)
def test_reminder_days(conn: sqlite3.Connection, now: datetime, periods: list[str]) -> None:
    buy(conn, "2026-10-10", 3)
    assert [m.period for m in card_msgs(conn, now)] == periods


def test_reminder_text_and_not_repeated(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-10-10", 3)
    now = datetime(2026, 10, 26, 7, 0, tzinfo=WAW)
    (msg,) = card_msgs(conn, now)
    assert msg.title == "Karta kredytowa — 3/5"
    assert msg.text.startswith("Brakuje 2 z 5 płatności kartą — miesiąc kończy się 31.10")
    summary.mark_sent(conn, msg)
    assert card_msgs(conn, now) == []


def test_no_reminder_when_met(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-10-10", 5)
    now = datetime(2026, 10, 26, 7, 0, tzinfo=WAW)
    assert card_msgs(conn, now) == []


def test_inbox_item_in_last_days(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-10-10", 4)
    assert card_items(conn, datetime(2026, 10, 25, 12, 0, tzinfo=WAW)) == []
    (item,) = card_items(conn, datetime(2026, 10, 26, 12, 0, tzinfo=WAW))
    assert item.count == 1 and item.severity == "warn"
    assert item.link == f"/transactions?account={CARD}&date_from=2026-10-01&date_to=2026-10-31"


def test_entity(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-10-10", 2)
    (e,) = ha_publisher.card_entities(Snapshot(conn), date(2026, 10, 20))
    assert e.key == "card_purchases_month" and e.state == "2"
    assert e.attributes == {"threshold": 5, "missing": 3, "month": "2026-10"}


async def test_home_tile(service: Service, monkeypatch: pytest.MonkeyPatch) -> None:
    service.conn.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (2, 'card', 'PLN', ?)",
        (now_iso(),),
    )
    buy(service.conn, "2026-10-10", 3)
    monkeypatch.setattr(service, "now", lambda: datetime(2026, 10, 20, 12, 0, tzinfo=WAW))
    async with _client(service) as client:
        page = (await client.get("/")).text
        past = (await client.get("/?month=2026-09")).text
    assert "Karta kredytowa" in page and "3 / 5" in page and "Brakuje 2 do 31.10" in page
    assert "Karta kredytowa" not in past
