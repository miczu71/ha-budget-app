"""M26 E3: ekran „Majątek”, kafel na Podsumowaniu i pola aktywa (powiązanie, data wartości)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import httpx
import pytest

from budget import invest, networth
from budget.service import Service
from budget.storage import db

from .test_savings import make as make_savings
from .test_web import INGRESS, _client

__all__ = ["service"]
from .test_web import service


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


async def test_empty_page_renders_with_tab_and_no_chart(client: httpx.AsyncClient) -> None:
    r = await client.get("/networth")
    assert r.status_code == 200
    assert f'href="{INGRESS}/networth"' in r.text and "Wykres pojawi się" in r.text


async def test_page_shows_balance_trend_and_stale(
    client: httpx.AsyncClient, service: Service
) -> None:
    c = service.conn
    invest.save_asset(c, None, "bonds", "EDO 2025", "5000", None, None, None, False, "2025-01-01")
    for day, total in (("2026-08-31", "1000"), ("2026-09-30", "3000")):
        c.execute(
            "INSERT INTO networth_snapshot "
            "(day, total, assets, liabilities, components_json, approx) "
            "VALUES (?, ?, ?, '0', '[]', 1)",
            (day, total, total),
        )
    page = (await client.get("/networth")).text
    assert "EDO 2025" in page and "Do aktualizacji" in page
    assert "Zmiana m/m" in page and "przybliżone" in page and 'class="nw-dot approx"' in page


async def test_page_marks_missing_stocks_history_and_shows_vesting(
    client: httpx.AsyncClient, service: Service
) -> None:
    c = service.conn
    c.execute(
        "INSERT INTO networth_snapshot (day, total, assets, liabilities, components_json, approx) "
        "VALUES ('2026-06-30', '1000', '1000', '0', '[]', 1)"
    )
    assert "brak danych o akcjach" not in (await client.get("/networth")).text
    db.kv_set(
        c,
        "stocks_nokia",
        {
            "market_value": "1000",
            "unvested_qty": "500",
            "price": "20.5",
            "next_vest": "2026-12-01",
            "next_vest_qty": "100",
            "fetched_at": service.now().isoformat(),
        },
    )
    page = (await client.get("/networth")).text
    assert "Przed 01.07.2026 brak danych o akcjach" in page
    assert "vesting 01.12.2026: 100 akcji" in page


async def test_home_tile_links_to_networth(client: httpx.AsyncClient, service: Service) -> None:
    invest.save_asset(service.conn, None, "bonds", "EDO 2025", "5000", None, None, None, False)
    page = (await client.get("/")).text
    assert "networth-tile" in page and f'href="{INGRESS}/networth"' in page


async def test_asset_form_sets_value_date_and_savings_link(
    client: httpx.AsyncClient, service: Service
) -> None:
    sid = make_savings(service.conn)
    form = {
        "kind": "bonds",
        "name": "EDO",
        "amount": "5000",
        "valued_at": "2026-05-01",
        "savings_id": str(sid),
    }
    assert (await client.post("/invest/assets", data=form)).status_code == 303
    (a,) = invest.all_assets(service.conn)
    assert a.valued_at == date(2026, 5, 1) and a.savings_id == sid
    nw = networth.compute(service.conn, date(2026, 10, 20))
    assert not [c for c in nw.components if c.group == networth.INVESTMENTS]  # liczone raz, z M10
    future = await client.post("/invest/assets", data={**form, "valued_at": "2999-01-01"})
    assert future.status_code == 303 and len(invest.all_assets(service.conn)) == 1
    assert Decimal(a.amount) == 5000
