"""Panel M5a: ekran Budżet (kwota, „zostało”, tempo) i grupa budżetu w Kategoriach."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from budget.categorize import taxonomy
from budget.service import Service

from .test_web import INGRESS, _client
from .test_web_categorize import DAY, _seed

__all__ = ["service"]
from .test_web import service

MONTH = DAY[:7]


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


async def test_nav_and_empty_budget(client: httpx.AsyncClient) -> None:
    r = await client.get("/budget")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert "Ile możesz wydać" in r.text
    assert f'action="{INGRESS}/budget/amount"' in r.text
    assert f'href="{INGRESS}/budget"' in (await client.get("/")).text


async def test_set_budget_and_remaining(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)  # elastyczne: 50 + 30 + 200 = 280
    page = (await client.get("/budget")).text
    assert "Ile możesz wydać" in page and "280,00" in page

    r = await client.post("/budget/amount", data={"month": MONTH, "amount": "1 000,00"})
    assert r.status_code == 303 and r.headers["location"] == f"{INGRESS}/budget?month={MONTH}"
    page = (await client.get(f"/budget?month={MONTH}")).text
    assert "— od miesiąca:" in page
    assert "Zostało na elastyczne" in page
    assert "720,00" in page  # 1000 − 280
    assert "Na dzień do końca miesiąca" in page and 'class="mark"' in page
    assert "Spożywcze" in page and "Paliwo" in page
    assert f"{INGRESS}/transactions?category=" in page
    assert "obowiązuje od" in page

    await client.post("/budget/amount", data={"month": MONTH, "amount": "zero"})
    assert "Podaj kwotę budżetu" in (await client.get("/budget")).text


async def test_category_group_form(client: httpx.AsyncClient, service: Service) -> None:
    page = (await client.get("/categories")).text
    assert f'action="{INGRESS}/categories/110/group"' in page
    r = await client.post("/categories/120/group", data={"flex_group": "flexible"})
    assert r.status_code == 303
    page = (await client.get("/categories")).text
    assert "„Media i energia” — grupa budżetu: elastyczne." in page
    assert taxonomy.all_categories(service.conn)[120].flex_group == "flexible"
    await client.post("/categories/3/group", data={"flex_group": "fixed"})
    assert "Grupę budżetu ma tylko podkategoria" in (await client.get("/categories")).text
