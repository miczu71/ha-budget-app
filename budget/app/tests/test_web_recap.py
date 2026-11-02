"""M25 E3: ekran „Rok w liczbach” — wybór roku, bloki, zakładka, stany puste."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from budget.service import Service

from .test_categorize_engine import add
from .test_web import INGRESS, _client

__all__ = ["service"]
from .test_web import service


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


def seed(service: Service) -> None:
    c = service.conn
    c.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', 'x')"
    )
    add(c, "3000", "transfer_in", "Pensja", day="2025-01-01")
    add(c, "-400", "card", "Sklep X", day="2025-03-10", category_id=110)
    now = service.now().date()
    add(c, "5000", "transfer_in", "Pensja", day=f"{now.year}-01-05")
    add(c, "-1000", "card", "Sklep X", day=f"{now.year}-01-10", category_id=110)


async def test_empty_ledger_renders_with_tab(client: httpx.AsyncClient) -> None:
    r = await client.get("/recap")
    assert r.status_code == 200
    assert f'href="{INGRESS}/recap"' in r.text and "Brak transakcji" in r.text


async def test_current_year_default_shows_blocks_and_year_switch(
    client: httpx.AsyncClient, service: Service
) -> None:
    seed(service)
    now = service.now().date()
    page = (await client.get("/recap")).text
    assert f"Rok w liczbach — {now.year}" in page
    for block in ("recap-totals", "recap-months", "recap-merchants", "recap-records"):
        assert f'id="{block}"' in page
    assert f'href="{INGRESS}/recap?year={now.year - 1}"' in page
    assert "Sklep" in page and "Gdzie wydajesz więcej" in page


async def test_first_year_has_no_yoy_blocks(client: httpx.AsyncClient, service: Service) -> None:
    seed(service)
    page = (await client.get("/recap?year=2025")).text
    assert "Rok w liczbach — 2025" in page
    assert "Brak danych za 2024" in page and "Gdzie wydajesz więcej" not in page


@pytest.mark.parametrize("bad", ["abc", "1999", "2999", "-1", ""])
async def test_invalid_year_falls_back_to_default(
    client: httpx.AsyncClient, service: Service, bad: str
) -> None:
    seed(service)
    now = service.now().date()
    page = (await client.get(f"/recap?year={bad}")).text
    assert f"Rok w liczbach — {now.year}" in page


def test_default_year_in_january_is_previous() -> None:
    from datetime import date

    from budget.web.routes_recap import default_year

    assert default_year([2026, 2025], date(2026, 1, 15)) == 2025
    assert default_year([2026], date(2026, 1, 15)) == 2026
    assert default_year([2026, 2025], date(2026, 2, 1)) == 2026
