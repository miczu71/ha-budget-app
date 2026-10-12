"""Panel M10 E1: ekran „Skarbonki” i przypisanie wydatku do skarbonki."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from budget.service import Service
from budget.storage.db import now_iso

from .test_categorize_engine import add
from .test_web import INGRESS, _client

__all__ = ["service"]
from .test_web import service

NUMBER = "11 2222 3333 4444 5555 6666 7777"  # fikcyjny
NEW = {"name": "Wakacje", "account_number": NUMBER, "target": "1200", "due_date": "2099-01-15"}


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    service.conn.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', ?)",
        (now_iso(),),
    )
    async with _client(service) as c:
        yield c


async def test_create_shows_masked_number(client: httpx.AsyncClient) -> None:
    page = (await client.get("/piggy")).text
    assert "Nowa skarbonka" in page and f'href="{INGRESS}/piggy"' in page
    r = await client.post("/piggy", data=NEW)
    assert r.status_code == 303
    page = (await client.get("/piggy")).text
    assert "Wakacje" in page and "PL** **** … 7777" in page
    assert "22223333" not in page.replace(" ", "")  # pełny numer nie trafia do panelu


async def test_bad_number_is_an_error(client: httpx.AsyncClient) -> None:
    await client.post("/piggy", data={**NEW, "account_number": "123"})
    assert "26 cyfr" in (await client.get("/piggy")).text


async def test_edit_keeps_number_when_left_empty(
    client: httpx.AsyncClient, service: Service
) -> None:
    await client.post("/piggy", data=NEW)
    await client.post("/piggy/1", data={**NEW, "name": "Urlop", "account_number": ""})
    row = service.conn.execute("SELECT name, account_number FROM piggy").fetchone()
    assert tuple(row) == ("Urlop", "11222233334444555566667777")


async def test_assign_expense_from_transactions(
    client: httpx.AsyncClient, service: Service
) -> None:
    await client.post("/piggy", data=NEW)
    txn = add(service.conn, "-300.00", "card", "HOTEL", "HOTEL X")
    assert 'class="piggy-pick"' in (await client.get("/transactions")).text
    r = await client.post(f"/transactions/{txn}/piggy", data={"piggy_id": "1"})
    assert "selected>ze skarbonki: Wakacje" in r.text
    assert "Wydane ze skarbonki: 300,00" in (await client.get("/piggy")).text


async def test_recurring_marks_series_with_piggy(
    client: httpx.AsyncClient, service: Service
) -> None:
    from .test_flex import serie

    with_piggy, without = serie(service.conn, "f1", "40"), serie(service.conn, "f2", "50")
    await client.post(
        "/piggy", data={"name": "Wakacje", "account_number": NUMBER, "series_id": str(with_piggy)}
    )
    page = (await client.get("/recurring")).text
    assert page.count("Skarbonka: Wakacje") == 1
    assert f'href="{INGRESS}/piggy#piggy-' in page
    assert f"/recurring/{without}" in page  # druga seria jest na liście, bez znacznika


async def test_savings_account_balance_and_masked_number(
    client: httpx.AsyncClient, service: Service
) -> None:
    form = {
        "name": "Oszczędnościowe",
        "account_number": NUMBER,
        "opening_balance": "1000",
        "opening_date": "2026-09-01",
    }
    assert (await client.post("/savings", data=form)).status_code == 303
    add(
        service.conn,
        "-250",
        "transfer_out",
        "wpłata",
        "JA",
        day="2026-09-10",
        counterparty_account="PL" + NUMBER.replace(" ", ""),
    )
    page = (await client.get("/piggy")).text
    assert "Oszczędnościowe" in page and "PL** **** … 7777" in page
    assert "1\u202f250,00" in page
    assert "22223333" not in page.replace(" ", "")
    await client.post("/savings/1/archive")
    assert "PL** **** … 7777" not in (await client.get("/piggy")).text


async def test_savings_page_shows_interest_and_promo(client: httpx.AsyncClient) -> None:
    form = {
        "name": "Oszczędnościowe",
        "account_number": NUMBER,
        "opening_balance": "10000",
        "opening_date": "2026-01-01",
        "base_rate": "3,65",
        "promo_rate": "6",
        "promo_limit": "5000",
        "promo_until": "2099-01-31",
    }
    assert (await client.post("/savings", data=form)).status_code == 303
    page = (await client.get("/piggy")).text
    assert "Odsetki (szac., netto)" in page and "Promocja" in page and "limit" in page
    bad = await client.post("/savings", data={**form, "name": "Inne", "promo_until": ""})
    assert bad.status_code == 303
    assert "datę końca promocji" in (await client.get("/piggy")).text
