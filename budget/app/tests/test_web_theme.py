"""Panel M13 E1b: przełącznik motywu wyglądu (Copilot / Monarch) zapisany w kv."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from budget.service import Service
from budget.storage import db
from budget.web.common import THEME_KEY

from .test_web import INGRESS, _client

__all__ = ["service"]
from .test_web import service


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


async def test_default_theme_is_copilot(client: httpx.AsyncClient) -> None:
    page = (await client.get("/")).text
    assert 'data-theme="copilot"' in page and 'name="color-scheme" content="dark"' in page
    assert 'name="theme-color" content="#000814"' in page


async def test_switch_to_monarch_and_back(client: httpx.AsyncClient, service: Service) -> None:
    r = await client.post("/theme", data={"theme": "monarch", "back": "/budget?month=2026-09"})
    assert r.status_code == 303 and r.headers["location"] == f"{INGRESS}/budget?month=2026-09"
    assert db.kv_get(service.conn, THEME_KEY) == "monarch"
    page = (await client.get("/")).text
    assert 'data-theme="monarch"' in page and 'name="color-scheme" content="light"' in page
    assert 'name="theme-color" content="#efecea"' in page
    assert 'value="monarch" class="theme-opt on"' in page  # aktywny motyw w menu
    await client.post("/theme", data={"theme": "copilot"})
    assert 'data-theme="copilot"' in (await client.get("/")).text


async def test_unknown_theme_is_rejected(client: httpx.AsyncClient, service: Service) -> None:
    await client.post("/theme", data={"theme": "monarch"})
    r = await client.post("/theme", data={"theme": "neon"})
    assert r.status_code == 303
    assert "Nieznany motyw" in (await client.get("/")).text
    assert db.kv_get(service.conn, THEME_KEY) == "monarch"  # bez zmiany


async def test_back_never_leaves_the_panel(client: httpx.AsyncClient) -> None:
    for back in ("https://evil.example/", "//evil.example", "evil"):
        r = await client.post("/theme", data={"theme": "monarch", "back": back})
        assert r.headers["location"] == f"{INGRESS}/", back


async def test_corrupt_stored_value_falls_back(client: httpx.AsyncClient, service: Service) -> None:
    db.kv_set(service.conn, THEME_KEY, "zepsuty")
    assert 'data-theme="copilot"' in (await client.get("/")).text


async def test_serif_font_is_served(client: httpx.AsyncClient) -> None:
    r = await client.get("/static/fonts/SourceSerif4-latin.woff2")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
