"""Panel M9 E1: ekran „Kredyt”."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from budget.service import Service
from budget.storage import db

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


async def test_calc_verdict_flips_with_savings_rate(client: httpx.AsyncClient) -> None:
    await client.post("/loan", data=NEW)
    page = (await client.get("/loan")).text
    assert 'hx-get="' in page and "/loan/1/calc" in page and "Nadpłata dziś" in page
    base = "/loan/1/calc?lump=20000&table=1&months="
    low = (await client.get(f"{base}&savings_rate=1")).text
    assert "Nadpłata wychodzi lepiej" in low and low.count("p.p.</th>") == 5
    high = (await client.get(f"{base}&savings_rate=30")).text
    assert "Oszczędności wychodzą lepiej" in high
    idle = (await client.get("/loan/1/calc?table=1")).text
    assert "Bez nadpłaty:" in idle and "Krótszy okres" in idle


async def test_calc_wibor_table_only_when_open(client: httpx.AsyncClient) -> None:
    await client.post("/loan", data=NEW)
    closed = (await client.get("/loan/1/calc?lump=20000&table=0")).text
    assert "Porównaj warianty" in closed and "loan-table" not in closed
    opened = (await client.get("/loan/1/calc?lump=20000&table=1&wibor_step=0.5")).text
    assert "loan-table" in opened and "-0,5 p.p." in opened and "-2 p.p." not in opened
    assert (
        "+1 p.p." in opened and "+0,5 p.p." in opened and '<option value="0.5" selected>' in opened
    )
    bad = (await client.get("/loan/1/calc?lump=20000&table=1&wibor_step=7")).text
    assert "+2 p.p." in bad  # nieznany krok → 1 p.p.


async def test_calc_reports_bad_input_and_unknown_loan(client: httpx.AsyncClient) -> None:
    await client.post("/loan", data=NEW)
    assert "skrócenie" in (await client.get("/loan/1/calc?variant=zzz")).text
    assert "niepoprawna kwota" in (await client.get("/loan/1/calc?lump=abc")).text
    assert "Nie ma takiego kredytu" in (await client.get("/loan/9/calc")).text


async def test_forecast_shows_after_reset_date_and_quote(
    client: httpx.AsyncClient, service: Service
) -> None:
    await client.post("/loan", data={**NEW, "rate_reset_date": "2098-12-09"})
    assert "rata ≈" not in (await client.get("/loan")).text  # jeszcze bez notowań WIBOR
    db.kv_set(service.conn, "wibor", {"quotes": {"2026-01-02": "5.50"}})
    page = (await client.get("/loan")).text
    assert "rata ≈" in page and "WIBOR 3M 5.50% z 02.01" in page and "wyższa o" in page
    assert 'name="rate_reset_date"' in page
