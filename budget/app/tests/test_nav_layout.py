"""M28: zakładki u góry — kolejność, ukrywanie, przypięte Podsumowanie."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import AsyncIterator

import httpx
import pytest

from budget import nav_layout as N
from budget.service import Service
from budget.storage import db

from .test_categorize_engine import conn
from .test_web import _client, service

__all__ = ["conn", "service"]


def _keys(conn: sqlite3.Connection) -> list[str]:
    return [t.key for t in N.layout.load(conn)]


def test_default_is_all_tabs_with_home_first(conn: sqlite3.Connection) -> None:
    assert _keys(conn) == list(N.TABS) and _keys(conn)[0] == "home"


def test_home_is_pinned_and_nothing_passes_it(conn: sqlite3.Connection) -> None:
    N.layout.move(conn, "home", 1)
    N.layout.toggle(conn, "home")
    N.layout.move(conn, "budget", -1)  # budżet już tuż za Podsumowaniem
    assert _keys(conn)[:2] == ["home", "budget"]
    assert not any(t.hidden for t in N.layout.load(conn))


def test_move_toggle_reset(conn: sqlite3.Connection) -> None:
    N.layout.move(conn, "ask", -1)
    assert _keys(conn)[6:9] == ["spending", "ask", "card"]
    N.layout.toggle(conn, "card")
    assert [t.key for t in N.layout.load(conn) if t.hidden] == ["card"]
    N.layout.reset(conn)
    assert _keys(conn) == list(N.TABS)


def test_saved_home_not_first_is_still_first(conn: sqlite3.Connection) -> None:
    db.kv_set(conn, N.KEY, {"order": ["loan", "home"], "hidden": ["home"]})
    keys = _keys(conn)
    assert keys[:2] == ["home", "loan"] and not N.layout.load(conn)[0].hidden


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


def _nav(page: str) -> list[str]:
    nav = page.split("<nav", 1)[1].split("</nav>", 1)[0]
    return re.findall(r">([^<]+)</a>", nav)


async def test_nav_follows_saved_order_and_hides(client: httpx.AsyncClient) -> None:
    assert _nav((await client.get("/")).text)[:3] == ["Podsumowanie", "Budżet", "Oszczędności"]
    await client.post("/tabs/move", data={"key": "loan", "delta": "-1"})
    await client.post("/tabs/toggle", data={"key": "budget"})
    names = _nav((await client.get("/loan")).text)
    assert names[:3] == ["Podsumowanie", "Kredyt", "Oszczędności"] and "Budżet" not in names
    assert (await client.get("/budget")).status_code == 200  # ukryta nadal działa z URL
    await client.post("/tabs/reset")
    assert "Budżet" in _nav((await client.get("/")).text)


async def test_tabs_page_and_htmx_partial(client: httpx.AsyncClient) -> None:
    page = (await client.get("/tabs")).text
    assert 'id="layout"' in page and "zawsze pierwsza" in page and "/tabs/move" in page
    r = await client.post("/tabs/toggle", data={"key": "ask"}, headers={"hx-request": "true"})
    assert r.status_code == 200 and "<nav" not in r.text and "(ukryty)" in r.text
    assert (await client.post("/tabs/toggle", data={"key": "x"})).status_code == 400
    assert (await client.post("/tabs/move", data={"key": "ask", "delta": "2"})).status_code == 400
