"""Panel M13: strona główna (podsumowanie budżetu), nawigacja z menu, Status pod `/status`."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

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


async def test_home_without_budget_invites_to_set_it(client: httpx.AsyncClient) -> None:
    page = (await client.get("/")).text
    assert "Podsumowanie" in page and "Ustaw budżet" in page
    assert f'href="{INGRESS}/budget"' in page and "Nic nie czeka na decyzję" in page


async def test_home_shows_flex_remaining(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)  # elastyczne: 280
    await client.post("/budget/amount", data={"month": MONTH, "amount": "1000"})
    page = (await client.get("/")).text
    assert "Zostało na elastyczne" in page and "720,00" in page
    assert "Na dzień do końca miesiąca" in page and 'class="mark"' in page


async def test_status_is_last_in_the_menu_not_in_the_bar(client: httpx.AsyncClient) -> None:
    page = (await client.get("/")).text
    bar, menu = page.split('class="more-panel"')
    assert f"{INGRESS}/status" not in bar and f"{INGRESS}/rules" not in bar
    order = [menu.index(f'href="{INGRESS}/{p}"') for p in ("review", "rules", "bank", "status")]
    assert order == sorted(order)


async def test_status_page_moved_to_status(client: httpx.AsyncClient) -> None:
    r = await client.get("/status")
    assert r.status_code == 200 and "<h1>Status</h1>" in r.text
    assert 'class="more on"' in r.text  # aktywna strona podświetla menu


async def test_fonts_are_served_immutable(client: httpx.AsyncClient) -> None:
    for name in ("InterVariable.woff2", "SpaceGrotesk-wght.woff2"):
        r = await client.get(f"/static/fonts/{name}")
        assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
