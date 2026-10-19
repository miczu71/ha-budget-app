"""Panel M22 E1: ekran „Inwestycje” — koszyki, aktywa, oferty, ustawienia."""

from __future__ import annotations

from collections.abc import AsyncIterator
from zoneinfo import ZoneInfo

import httpx
import pytest

from budget import invest, invest_sources, promo_track
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


async def test_blog_offer_form_confirms_with_fixes_and_status_shows_accuracy(
    client: httpx.AsyncClient, service: Service
) -> None:
    service.conn.execute(
        "INSERT INTO invest_offer (kind, bank, rate, months, source, status, url, extracted, "
        "created_at) VALUES ('deposit', 'Bank A', '5', 5, 'blog', 'review', 'https://x.example/a', "
        '\'{"rate": "5", "limit_amount": null, "months": 5, "bank": "Bank A"}\', '
        "'2026-10-19T07:00:00')"
    )
    page = (await client.get("/invest")).text
    assert "z bloga (model AI)" in page and 'name="rate" value="5' in page
    bad = await client.post("/invest/offers/1/confirm", data={"bank": "Bank A", "rate": "abc"})
    assert bad.status_code == 303 and invest.all_offers(service.conn)[0].status == "review"
    form = {"bank": "Bank A", "rate": "5,5", "months": "5", "limit_amount": "", "conditions": ""}
    await client.post("/invest/offers/1/confirm", data=form)
    assert invest.blog_accuracy(service.conn) == (0, 1)
    service.settings = service.settings.model_copy(update={"ai_base_url": "http://r/v1"})
    status = (await client.get("/status")).text
    assert "Oferty z blogów — trafność" in status and "0 z 1 ocenionych" in status


async def test_promo_flow_from_offer_to_paid_bonus(
    client: httpx.AsyncClient, service: Service
) -> None:
    await client.post(
        "/invest/offers",
        data={"kind": "account", "bank": "Bank X", "rate": "6", "months": "3", "conditions": "x"},
    )
    (offer,) = invest.all_offers(service.conn)
    r = await client.post(f"/invest/offers/{offer.id}/track")
    assert r.status_code == 303
    page = (await client.get("/invest")).text
    assert "Promocje w toku" in page and "Bank X" in page and "Skorzystaj" not in page
    (track,) = promo_track.tracks(service.conn)
    base = f"/invest/promos/{track.id}"
    await client.post(f"{base}/conditions", data={"kind": "manual", "label": "Aplikacja"})
    await client.post(f"{base}/bonus", data={"bonus": "250"})
    cond = promo_track.tracks(service.conn)[0].conditions[0]
    page = (await client.get("/invest")).text
    assert "Aplikacja" in page and "Premia odebrana" not in page
    await client.post(f"/invest/promos/conditions/{cond.id}/toggle")
    assert "Premia odebrana" in (await client.get("/invest")).text
    await client.post(f"{base}/paid", data={"paid_to": "asset"})
    assert promo_track.tracks(service.conn)[0].status == "paid"
    assert invest.assets_total(service.conn) == 250


async def test_promo_errors_are_flashed_not_raised(client: httpx.AsyncClient) -> None:
    r = await client.post("/invest/offers/999/track")
    assert r.status_code == 303
    r = await client.post("/invest/promos/999/paid", data={"paid_to": "asset"})
    assert r.status_code == 303
