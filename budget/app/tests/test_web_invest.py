"""Panel M22 E1: ekran „Inwestycje” — koszyki, aktywa, oferty, ustawienia."""

from __future__ import annotations

from collections.abc import AsyncIterator
from zoneinfo import ZoneInfo

import httpx
import pytest

from budget import invest, invest_sources
from budget.service import Service

from .test_web import INGRESS, _client

__all__ = ["service"]
from .test_web import service

WARSAW = ZoneInfo("Europe/Warsaw")


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


async def test_page_renders_empty_with_tab_and_no_projection(client: httpx.AsyncClient) -> None:
    r = await client.get("/invest")
    assert r.status_code == 200
    page = r.text
    assert f'href="{INGRESS}/invest"' in page  # zakładka w nawigacji
    assert "Trzy koszyki" in page and "Brak prognozy rocznej" in page
    assert "ETF w IKE" in page  # porównanie działa bez żadnych danych (kwota przykładowa)


async def test_add_asset_shows_in_bucket_and_can_be_archived(
    client: httpx.AsyncClient, service: Service
) -> None:
    form = {"kind": "bonds", "name": "EDO 2025", "amount": "5 000", "rate": "5,6", "ike": "1"}
    assert (await client.post("/invest/assets", data=form)).status_code == 303
    page = (await client.get("/invest")).text
    assert 'stat-value">EDO 2025' in page and "5\u202f000,00" in page and "IKE" in page
    await client.post("/invest/assets/1/archive")
    assert 'stat-value">EDO 2025' not in (await client.get("/invest")).text
    assert invest.assets_total(service.conn) == 0


async def test_bad_asset_is_an_error_not_saved(client: httpx.AsyncClient, service: Service) -> None:
    await client.post("/invest/assets", data={"kind": "bonds", "name": "", "amount": "100"})
    assert "Podaj nazwę aktywa" in (await client.get("/invest")).text
    assert invest.all_assets(service.conn) == []


async def test_offer_enters_the_ranking(client: httpx.AsyncClient) -> None:
    form = {"kind": "deposit", "bank": "Bank A", "rate": "5", "months": "12"}
    await client.post("/invest/offers", data=form)
    page = (await client.get("/invest?amount=10000&years=1")).text
    assert "Lokata Bank A" in page and "405,00" in page.replace("\xa0", " ")


async def test_indexed_bond_without_margin_is_rejected(client: httpx.AsyncClient) -> None:
    await client.post("/invest/offers", data={"kind": "edo", "bank": "Skarb", "rate": "6"})
    assert "wymagają marży" in (await client.get("/invest")).text


async def test_settings_change_cushion(client: httpx.AsyncClient, service: Service) -> None:
    data = {"cushion_months": "6", "etf_returns": "0; 5; 8", "etf_ter": "0,3", "inflation": "2,5"}
    await client.post("/invest/settings", data=data)
    assert invest.load_settings(service.conn).cushion_months == 6
    await client.post("/invest/settings", data={**data, "cushion_months": "0"})
    assert "od 1 do 24" in (await client.get("/invest")).text
    assert invest.load_settings(service.conn).cushion_months == 6


async def test_banks_hide_new_client_offers_and_review_offers_can_be_confirmed(
    client: httpx.AsyncClient, service: Service
) -> None:
    from .test_invest_sources import NOW as NAIVE
    from .test_invest_sources import PAGES, feed

    await invest_sources.refresh(service.conn, NAIVE.replace(tzinfo=WARSAW), feed(PAGES))
    page = (await client.get("/invest?amount=10000&years=1")).text
    assert "Lokata VeloBank" in page and "Do sprawdzenia" in page and "opis oferty" in page
    assert "pobrane 19.10 07:00" in page

    assert (await client.post("/invest/banks", data={"name": "velobank"})).status_code == 303
    page = (await client.get("/invest?amount=10000&years=1")).text
    assert "Lokata VeloBank" not in page and "jesteś klientem tego banku" in page
    await client.post("/invest/banks", data={"name": "VELOBANK"})
    assert "już jest na liście" in (await client.get("/invest")).text

    await client.post("/invest/banks/1/delete")
    assert invest.all_banks(service.conn) == []
    review = next(o for o in invest.all_offers(service.conn) if o.status == "review")
    await client.post(f"/invest/offers/{review.id}/confirm", data={"bank": "Bank Beta"})
    assert "Bank Beta" in (await client.get("/invest")).text


async def test_source_error_is_visible_on_the_page(
    client: httpx.AsyncClient, service: Service
) -> None:
    from .test_invest_sources import NOW as NAIVE
    from .test_invest_sources import feed

    await invest_sources.refresh(service.conn, NAIVE.replace(tzinfo=WARSAW), feed({}))
    assert "błąd odczytu od 19.10" in (await client.get("/invest")).text
