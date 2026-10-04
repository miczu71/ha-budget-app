"""Panel M5b E1: dzwonek (centrum powiadomień), ekran Cykliczne, encja `sensor.budget_inbox`."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from budget import ha_publisher, inbox
from budget.categorize.rules import Conditions
from budget.recurring import series as S
from budget.service import Service
from budget.storage.db import now_iso

from .test_categorize_engine import add
from .test_web import INGRESS, _client

__all__ = ["service"]
from .test_web import service

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


def _account(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO account (id, kind, currency, display_name, created_at) "
        "VALUES (1, 'current', 'PLN', 'Rachunek', ?)",
        (now_iso(),),
    )


def _subscription(conn: sqlite3.Connection, name: str = "Qwertyflix Sp") -> None:
    today = date.today()
    for back in range(4, 0, -1):
        y, m = divmod(today.year * 12 + today.month - 1 - back, 12)
        add(conn, "-43.00", "transfer_out", f"Abonament {back}", name, day=f"{y}-{m + 1:02}-10")


def test_inbox_items(service: Service) -> None:
    conn = service.conn
    _account(conn)
    memo = inbox.BalanceMemo()
    assert inbox.items(conn, NOW, memo) == []
    add(conn, "-10.00", "card", "Coś X", day="2026-10-02")
    add(conn, "-12.00", "card", "Coś Y", day="2026-09-30")
    add(conn, "-14.00", "card", "Coś Z", day="2026-08-30")  # dwa miesiące wstecz — nie
    conn.execute(
        "INSERT INTO sync_log (trigger, started_at, finished_at, status) "
        "VALUES ('schedule', ?, ?, 'error')",
        (now_iso(), now_iso()),
    )
    found = inbox.items(conn, NOW, memo)
    kinds = [(i.kind, i.count, i.link) for i in found]
    assert kinds[0] == ("sync_failures", 1, "/")  # błędy na górze
    assert ("uncategorized", 1, "/review?month=2026-10") in kinds
    assert ("uncategorized", 1, "/review?month=2026-09") in kinds
    assert len(found) == 3
    S.insert(
        conn,
        name="X",
        direction="out",
        cadence="M",
        conditions=Conditions(kind="loan", direction="out"),
        expected=Decimal("1"),
        tolerance=Decimal("0"),
        anchor_day=1,
        status="proposed",
        origin="detected",
        key="k",
    )
    assert any(i.kind == "series_proposed" for i in inbox.items(conn, NOW, memo))


def test_inbox_entity() -> None:
    items = [inbox.Item("uncategorized", "Bez kategorii — październik 2026", 3, "/review")]
    e = ha_publisher.inbox_entity(items)
    assert e.key == "inbox" and e.state == "1"
    assert e.attributes["items"][0] == {
        "kind": "uncategorized",
        "title": "Bez kategorii — październik 2026",
        "count": 3,
        "severity": "info",
    }
    _, payload = e.discovery()
    assert payload["default_entity_id"] == "sensor.budget_inbox"


async def test_bell_and_inbox_page(client: httpx.AsyncClient, service: Service) -> None:
    page = (await client.get("/")).text
    assert f'href="{INGRESS}/inbox"' in page and 'aria-label="Do decyzji: 0"' in page
    assert f'href="{INGRESS}/recurring"' in page
    assert "Nic nie czeka na decyzję" in (await client.get("/inbox")).text
    _account(service.conn)
    add(service.conn, "-10.00", "card", "Coś X", day=date.today().isoformat())
    page = (await client.get("/inbox")).text
    assert 'aria-label="Do decyzji: 1"' in page and "Bez kategorii" in page
    assert f'href="{INGRESS}/review?month={date.today():%Y-%m}"' in page


async def test_recurring_flow(client: httpx.AsyncClient, service: Service) -> None:
    conn = service.conn
    _account(conn)
    _subscription(conn)
    assert "Brak potwierdzonych serii" in (await client.get("/recurring")).text

    r = await client.post("/recurring/detect")
    assert r.status_code == 303 and r.headers["location"] == f"{INGRESS}/recurring"
    page = (await client.get("/recurring")).text
    assert "Nowe propozycje: 1." in page
    assert "Propozycje do potwierdzenia (1)" in page and "Qwertyflix Sp" in page
    assert "co miesiąc" in page and "4 wystąpień" in page
    [s] = S.all_series(conn)
    assert "Nowe płatności cykliczne" in (await client.get("/inbox")).text

    # edycja i potwierdzenie z formularza serii
    page = (await client.get(f"/recurring/{s.id}")).text
    assert f'action="{INGRESS}/recurring/{s.id}/save"' in page and "Zapisz i potwierdź" in page
    assert "Transakcje serii (4)" in page
    form = {
        "name": "Film",
        "cadence": "M",
        "expected_amount": "45,00",
        "tolerance": "5",
        "field_0": "merchant",
        "op_0": "equals",
        "value_0": s.conditions.text[0].value,
        "direction": "out",
        "confirm": "1",
    }
    r = await client.post(f"/recurring/{s.id}/save", data=form)
    assert r.status_code == 303
    page = (await client.get("/recurring")).text
    assert "Seria „Film” potwierdzona." in page and "Aktywne serie (1)" in page
    s = S.get(conn, s.id)
    assert s.status == "active" and str(s.expected_amount) == "45.00"
    assert "Nowe płatności cykliczne" not in (await client.get("/inbox")).text

    # błąd walidacji wraca na formularz
    r = await client.post(f"/recurring/{s.id}/save", data={**form, "direction": ""})
    assert r.headers["location"] == f"{INGRESS}/recurring/{s.id}"
    assert "kierunek" in (await client.get(f"/recurring/{s.id}")).text

    # zakończ / przywróć
    await client.post(f"/recurring/{s.id}/status", data={"action": "end"})
    page = (await client.get("/recurring")).text
    assert "Seria „Film” zakończona." in page and "Zakończone (1)" in page
    await client.post(f"/recurring/{s.id}/status", data={"action": "restore"})
    assert S.get(conn, s.id).status == "active"
    await client.post(f"/recurring/{s.id}/status", data={"action": "reject"})
    assert "jest aktywna" in (await client.get("/recurring")).text


async def test_reject_proposal(client: httpx.AsyncClient, service: Service) -> None:
    conn = service.conn
    _account(conn)
    _subscription(conn)
    service.detect_series()
    [s] = S.all_series(conn)
    r = await client.post(f"/recurring/{s.id}/status", data={"action": "reject"})
    assert r.status_code == 303
    page = (await client.get("/recurring")).text
    assert "nie będzie proponowana ponownie" in page and "Odrzucone propozycje: 1" in page
    assert service.detect_series() == []
    r = await client.get(f"/recurring/{s.id}")
    assert r.status_code == 303  # odrzuconej nie edytujemy
    assert (await client.post("/recurring/999/status", data={"action": "x"})).status_code == 303
