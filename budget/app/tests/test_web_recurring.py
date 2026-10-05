"""Panel M5b E1: dzwonek (centrum powiadomień), ekran Cykliczne, encja `sensor.budget_inbox`."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from budget import ha_publisher, inbox
from budget.categorize.rules import Conditions, TextCondition
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


async def test_this_month_section(client: httpx.AsyncClient, service: Service) -> None:
    conn = service.conn
    _account(conn)
    today = service.now().date()
    add(conn, "-43.00", "transfer_out", "Abonament", "Qwertyflix Sp", day=today.isoformat())
    S.insert(
        conn,
        name="Qwertyflix",
        direction="out",
        cadence="M",
        conditions=Conditions(
            text=(TextCondition("merchant", "equals", "Qwertyflix Sp"),), direction="out"
        ),
        expected=Decimal("43"),
        tolerance=Decimal("5"),
        anchor_day=today.day,
        status="active",
        origin="manual",
        key=None,
    )
    S.insert(
        conn,
        name="Czynsz wymyślony",
        direction="out",
        cadence="M",
        conditions=Conditions(
            text=(TextCondition("merchant", "equals", "Nikt Taki"),), direction="out"
        ),
        expected=Decimal("1000"),
        tolerance=Decimal("5"),
        anchor_day=min(today.day + 10, 28) if today.day < 18 else 28,
        status="active",
        origin="manual",
        key=None,
    )
    page = (await client.get("/recurring")).text
    assert "Ten miesiąc" in page and "zapłacone" in page and "Qwertyflix" in page
    assert "Jeszcze zejdzie" in page
    assert "Ten miesiąc" in (await client.get("/recurring?month=2020-01")).text


async def test_manual_series_from_transaction(client: httpx.AsyncClient, service: Service) -> None:
    conn = service.conn
    _account(conn)
    today = service.now().date()
    tid = add(conn, "-43.00", "transfer_out", "Abonament", "Qwertyflix Sp", day=today.isoformat())
    page = (await client.get("/transactions")).text
    assert f'href="{INGRESS}/recurring/new?txn={tid}"' in page and "to się powtarza" in page

    form = (await client.get(f"/recurring/new?txn={tid}")).text
    assert "Nowa płatność cykliczna" in form and 'value="Qwertyflix Sp"' in form
    assert (
        f'action="{INGRESS}/recurring/new"' in form
        and f'name="anchor_day" value="{today.day}"' in form
    )

    data = {
        "name": "Qwertyflix",
        "cadence": "M",
        "expected_amount": "43,00",
        "tolerance": "5",
        "anchor_day": str(today.day),
        "field_0": "merchant",
        "op_0": "equals",
        "value_0": "Qwertyflix Sp",
        "direction": "out",
    }
    pre = (await client.post("/recurring/new/preview", data=data)).text
    assert "obejmie 1 transakcję" in pre
    bad = (await client.post("/recurring/new/preview", data={**data, "expected_amount": "0"})).text
    assert "kwotę większą od zera" in bad

    r = await client.post("/recurring/new", data=data)
    assert r.status_code == 303
    [s] = S.all_series(conn)
    assert (s.status, s.origin, s.anchor_day) == ("active", "manual", today.day)
    assert s.group_key == S.group_key("Qwertyflix Sp", "out")
    assert r.headers["location"] == f"{INGRESS}/recurring/{s.id}"

    page = (await client.get("/transactions")).text
    assert "cykliczna: Qwertyflix" in page and "to się powtarza" not in page
    assert "zapłacone" in (await client.get("/recurring")).text

    r = await client.post("/recurring/new", data={**data, "name": ""})
    assert "Podaj nazwę" in (await client.get(r.headers["location"].removeprefix(INGRESS))).text
    assert len(S.all_series(conn)) == 1
