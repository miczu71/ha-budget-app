"""Panel M9 E1: ekran „Kredyt”."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from budget.service import Service

from .test_web import INGRESS, _client

__all__ = ["service"]
from .test_web import service

NEW = {
    "name": "Dom",
    "principal": "100000",
    "principal_date": "2099-01-21",
    "reference_rate": "4",
    "margin": "2",
    "installment_kind": "equal",
    "last_payment_date": "2100-01-20",
    "payment_day": "20",
}


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


async def test_create_shows_summary_and_schedule(client: httpx.AsyncClient) -> None:
    page = (await client.get("/loan")).text
    assert "Nowy kredyt" in page and f'href="{INGRESS}/loan"' in page
    assert (await client.post("/loan", data=NEW)).status_code == 303
    page = (await client.get("/loan")).text
    assert "Dom" in page and "Harmonogram" in page and "6.00%" in page
    assert "12 rat do spłaty" in page
    assert "20.02.99" in page and "&lt;li" not in page  # wiersze z makra jako HTML


async def test_bad_input_is_an_error_and_edit_updates(client: httpx.AsyncClient) -> None:
    await client.post("/loan", data={**NEW, "principal": "0"})
    assert "kapitał" in (await client.get("/loan")).text
    await client.post("/loan", data=NEW)
    await client.post("/loan/1", data={**NEW, "margin": "1,5"})
    assert "5.50%" in (await client.get("/loan")).text
    assert (await client.post("/loan/1/archive")).status_code == 303
    assert "Nowy kredyt" in (await client.get("/loan")).text
