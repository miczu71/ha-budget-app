"""Karta kredytowa per osoba (M15 E2): osoby, ręczne przypisanie, liczniki, dzwonek, ekran."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest

from budget import card, ha_publisher
from budget.service import Service
from budget.snapshot import Snapshot
from budget.storage.db import now_iso

from .test_card import WAW, buy, card_items, card_msgs, conn
from .test_web import _client, service

__all__ = ["conn", "service"]


def ids(c: sqlite3.Connection) -> list[int]:
    return [r[0] for r in c.execute("SELECT id FROM txn WHERE kind = 'card' ORDER BY id")]


def assign_all(c: sqlite3.Connection, txns: list[int], holder: int) -> None:
    for t in txns:
        card.assign(c, t, holder)


@pytest.fixture
def two(conn: sqlite3.Connection) -> tuple[int, int]:
    return card.add_holder(conn, "Osoba 1"), card.add_holder(conn, "Osoba 2")


def test_holders_validation(conn: sqlite3.Connection, two: tuple[int, int]) -> None:
    with pytest.raises(card.CardError):
        card.add_holder(conn, "  Osoba   1 ")
    with pytest.raises(card.CardError):
        card.add_holder(conn, "   ")
    card.rename_holder(conn, two[1], " Osoba  B ")
    assert [h["name"] for h in card.holders(conn)] == ["Osoba 1", "Osoba B"]
    with pytest.raises(card.CardError):
        card.rename_holder(conn, two[1], "Osoba 1")


def test_assign_only_card_payments(conn: sqlite3.Connection, two: tuple[int, int]) -> None:
    buy(conn, "2026-10-10")
    buy(conn, "2026-10-11", kind="card_refund", amount="10.00")
    pay, refund = (
        ids(conn)[0],
        conn.execute("SELECT id FROM txn WHERE kind = 'card_refund'").fetchone()[0],
    )
    card.assign(conn, pay, two[0])
    with pytest.raises(card.CardError):
        card.assign(conn, refund, two[0])
    with pytest.raises(card.CardError):
        card.assign(conn, pay, 999)
    assert (
        conn.execute("SELECT card_holder_id FROM txn WHERE id = ?", (pay,)).fetchone()[0] == two[0]
    )


def test_counts_per_holder_and_unassigned(conn: sqlite3.Connection, two: tuple[int, int]) -> None:
    buy(conn, "2026-10-10", 4)
    buy(conn, "2026-10-12", 2)
    p = ids(conn)
    assign_all(conn, p[:3], two[0])
    card.assign(conn, p[3], two[1])
    cm = card.month_status(conn, date(2026, 10, 20))
    assert cm is not None and cm.count == 6 and cm.unassigned == 2
    assert [(h.name, h.count, h.missing) for h in cm.holders] == [
        ("Osoba 1", 3, 2),
        ("Osoba 2", 1, 4),
    ]
    assert cm.missing == 6 and cm.needs_action


def test_holder_count_uses_conservative_dates(
    conn: sqlite3.Connection, two: tuple[int, int]
) -> None:
    buy(conn, "2026-10-01", 5)  # po dacie zakupu to jeszcze poprzedni miesiąc
    assign_all(conn, ids(conn), two[0])
    (first, _) = card.month_status(conn, date(2026, 10, 20)).holders  # type: ignore[union-attr]
    assert first.count == 0


def test_without_holders_one_shared_counter(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-10-05", 3)
    cm = card.month_status(conn, date(2026, 10, 20))
    assert cm is not None and cm.shared and cm.unassigned == 0
    assert [(h.name, h.count, h.missing) for h in cm.holders] == [("Razem", 3, 2)]
    card.add_holder(conn, "Osoba 1")
    cm = card.month_status(conn, date(2026, 10, 20))
    assert cm is not None and not cm.shared and cm.unassigned == 3


def test_inbox_assign_any_day_and_missing_per_holder(
    conn: sqlite3.Connection, two: tuple[int, int]
) -> None:
    buy(conn, "2026-10-05", 6)
    assign_all(conn, ids(conn)[:5], two[0])
    early = card_items(conn, datetime(2026, 10, 10, 12, 0, tzinfo=WAW))
    assert [(i.kind, i.count, i.severity) for i in early] == [("card_assign", 1, "info")]
    late = card_items(conn, datetime(2026, 10, 27, 12, 0, tzinfo=WAW))
    assert [(i.kind, i.count, i.severity) for i in late] == [
        ("card_assign", 1, "warn"),
        ("card_payments", 5, "warn"),
    ]
    assert (
        late[1].title == "Karta kredytowa: Osoba 2 — brakuje płatności" and late[1].link == "/card"
    )


def test_reminder_per_holder(conn: sqlite3.Connection, two: tuple[int, int]) -> None:
    buy(conn, "2026-10-05", 7)
    assign_all(conn, ids(conn)[:5], two[0])
    card.assign(conn, ids(conn)[5], two[1])
    (msg,) = card_msgs(conn, datetime(2026, 10, 26, 7, 0, tzinfo=WAW))
    assert msg.title == "Karta kredytowa — brakuje płatności"
    lines = msg.text.splitlines()
    assert lines[0] == "Osoba 1: 5/5 · Osoba 2: 1/5 (brakuje 4)"
    assert lines[1].startswith("Do przypisania: 1")


def test_reminder_only_unassigned(conn: sqlite3.Connection, two: tuple[int, int]) -> None:
    buy(conn, "2026-10-05", 11)
    p = ids(conn)
    assign_all(conn, p[:5], two[0])
    assign_all(conn, p[5:10], two[1])
    (msg,) = card_msgs(conn, datetime(2026, 10, 30, 7, 0, tzinfo=WAW))
    assert msg.title == "Karta kredytowa — płatności do przypisania"
    card.assign(conn, p[10], two[1])
    assert card_msgs(conn, datetime(2026, 10, 30, 7, 0, tzinfo=WAW)) == []


def test_entity_holders(conn: sqlite3.Connection, two: tuple[int, int]) -> None:
    buy(conn, "2026-10-05", 3)
    card.assign(conn, ids(conn)[0], two[0])
    (e,) = ha_publisher.card_entities(Snapshot(conn), date(2026, 10, 20))
    assert e.state == "3" and e.attributes["unassigned"] == 2
    assert e.attributes["holders"] == [
        {"name": "Osoba 1", "count": 1, "missing": 4},
        {"name": "Osoba 2", "count": 0, "missing": 5},
    ]


async def test_card_screen(service: Service, monkeypatch: pytest.MonkeyPatch) -> None:
    c = service.conn
    c.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (2, 'card', 'PLN', ?)",
        (now_iso(),),
    )
    buy(c, "2026-10-10", 2)
    monkeypatch.setattr(service, "now", lambda: datetime(2026, 10, 20, 12, 0, tzinfo=WAW))
    async with _client(service) as client:
        page = (await client.get("/card")).text
        assert "Dodaj osobę" in page and "Do przypisania" not in page  # bez osób
        await client.post("/card/holders", data={"name": "Osoba 1"})
        await client.post("/card/holders", data={"name": "Osoba 2"})
        holder = card.holders(c)[0]["id"]
        t = ids(c)[0]
        page = (
            await client.post(
                "/card/assign",
                data={"txn_id": str(t), "holder_id": str(holder), "month": "2026-10"},
            )
        ).text
        home = (await client.get("/")).text
        txns = (await client.get("/transactions")).text
    assert 'id="card-main"' in page and 'aria-pressed="true"' in page
    assert 'Osoba 1</span><span class="stat-value">1 / 5' in page
    assert "Przypisz płatności" in home and "Osoba 2" in home
    assert 'title="osoba, która zapłaciła kartą">Osoba 1</span>' in txns


# --- E3: historia z CSV -------------------------------------------------------------------

FULL, ONE = "1111222233330001", "1111222233330002"  # blok całego konta i blok jednej karty


def csv_rows(c: sqlite3.Connection, txns: list[int], one: list[int]) -> None:
    """Eksport jak z Millenetu: wszystko pod FULL (z txn_id), część pod ONE (duplikaty)."""
    for number in (FULL, ONE):
        c.execute(
            "INSERT INTO account_alias (source, value, account_id) VALUES ('csv_number', ?, 2)",
            (number,),
        )
    batch = c.execute(
        "INSERT INTO import_batch (source, fetched_at, created_at) VALUES ('csv', ?, ?)",
        (now_iso(), now_iso()),
    ).lastrowid

    def row(number: str, t: int, txn_id: int | None, status: str) -> None:
        c.execute(
            "INSERT INTO csv_row (number, row_key, tx_date, settle_date, kind_raw, kind, "
            "amount, currency, description, occurrence, seq, batch_id, txn_id, status) "
            "VALUES (?, ?, '2026-10-05', '2026-10-05', '', 'card', '-10.00', 'PLN', 'X', 0, "
            "?, ?, ?, ?)",
            (number, f"k{t}", t, batch, txn_id, status),
        )

    for t in txns:
        row(FULL, t, t, "inserted")
        if t in one:
            row(ONE, t, None, "duplicate")


def test_backfill_narrowest_block_wins(conn: sqlite3.Connection, two: tuple[int, int]) -> None:
    buy(conn, "2026-10-05", 4)
    p = ids(conn)
    csv_rows(conn, p, one=p[:3])
    card.set_csv_number(conn, two[1], FULL)
    assert card.backfill_from_csv(conn) is None  # nie każdy numer ma osobę — nic
    card.assign(conn, p[0], two[1])  # ręczne przypisanie zostaje
    card.set_csv_number(conn, two[0], ONE)
    assert card.backfill_from_csv(conn) == 3
    got = dict(conn.execute("SELECT id, card_holder_id FROM txn WHERE kind = 'card'").fetchall())
    assert [got[t] for t in p] == [two[1], two[0], two[0], two[1]]


def test_csv_number_validation(conn: sqlite3.Connection, two: tuple[int, int]) -> None:
    buy(conn, "2026-10-05")
    csv_rows(conn, ids(conn), one=[])
    with pytest.raises(card.CardError):
        card.set_csv_number(conn, two[0], "9999")
    card.set_csv_number(conn, two[0], FULL)
    with pytest.raises(card.CardError):
        card.set_csv_number(conn, two[1], FULL)
    card.set_csv_number(conn, two[0], None)


async def test_card_screen_csv_mapping(service: Service) -> None:
    c = service.conn
    c.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (2, 'card', 'PLN', ?)",
        (now_iso(),),
    )
    buy(c, "2026-10-05", 2)
    a, b = card.add_holder(c, "Osoba 1"), card.add_holder(c, "Osoba 2")
    p = ids(c)
    csv_rows(c, p, one=p[:1])
    async with _client(service) as client:
        page = (await client.get("/card")).text
        assert "…0002 (1 wierszy)" in page and "…0001 (2 wierszy)" in page
        await client.post(f"/card/holders/{b}/csv", data={"number": FULL})
        await client.post(f"/card/holders/{a}/csv", data={"number": ONE})
        page = (await client.get("/card")).text
    assert "przypisano płatności: 2" in page
