"""Panel M5a: ekran Budżet (kwota, „zostało”, tempo) i grupa budżetu w Kategoriach."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest

from budget.categorize import engine, taxonomy
from budget.categorize.rules import Conditions, TextCondition
from budget.recurring import series as S
from budget.service import Service

from .test_categorize_engine import add
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


async def test_auto_pool_breakdown_and_back_to_auto(
    client: httpx.AsyncClient, service: Service
) -> None:
    _seed(service.conn)
    prev = (date.fromisoformat(DAY) - timedelta(days=1)).replace(day=24)
    t = add(service.conn, "6000.00", "transfer_in", "Pensja", "FIRMA X", day=prev.isoformat())
    engine.set_manual(service.conn, t, taxonomy.by_slug(service.conn)["wynagrodzenie"].id)
    page = (await client.get(f"/budget?month={MONTH}")).text
    assert "— automatyczna, z wpływów z miesiąca:" in page
    assert "Pula automatyczna" in page and "6\u202f000,00" in page
    assert "Ustaw ręcznie od tego miesiąca" in page

    await client.post("/budget/amount", data={"month": MONTH, "amount": "1000"})
    page = (await client.get(f"/budget?month={MONTH}")).text
    assert "— ręczna, obowiązuje od miesiąca:" in page
    assert f'action="{INGRESS}/budget/auto"' in page

    r = await client.post("/budget/auto", data={"month": MONTH})
    assert r.status_code == 303
    page = (await client.get(f"/budget?month={MONTH}")).text
    assert "Pula automatyczna (z wpływów)" in page  # komunikat
    assert "— automatyczna, z wpływów z miesiąca:" in page


async def test_pool_components_and_fixed_editing(
    client: httpx.AsyncClient, service: Service
) -> None:
    conn = service.conn
    _seed(conn)
    slugs = taxonomy.by_slug(conn)
    prev = (date.fromisoformat(DAY) - timedelta(days=1)).replace(day=24)
    t = add(conn, "6000.00", "transfer_in", "Pensja", "FIRMA X", day=prev.isoformat())
    engine.set_manual(conn, t, slugs["wynagrodzenie"].id)
    t = add(conn, "-2300.00", "transfer_out", "Rata", "BANK Y", day=prev.replace(day=5).isoformat())
    engine.set_manual(conn, t, slugs["kredyt"].id)
    t = add(conn, "-80.00", "transfer_out", "Hotel", "HOTEL Z", day=prev.replace(day=6).isoformat())
    engine.set_manual(conn, t, slugs["noclegi"].id)
    engine.recategorize(conn)

    page = (await client.get(f"/budget?month={MONTH}")).text
    assert "Firma X" in page and "6 000,00" in page  # źródło wpływu
    assert 'id="fixed"' in page and 'id="fixed" open' not in page
    assert "Kredyt" in page and "2 300,00" in page
    kredyt, noclegi = slugs["kredyt"].id, slugs["noclegi"].id
    assert f'action="{INGRESS}/budget/fixed/{kredyt}"' in page  # przenieś ze stałych
    # wiersz stałej rozwija „Przenieś”; summary bez kotwicy, link do transakcji w rozwinięciu
    row = page.split('<details class="leaf">')[1].split("</details>")[0]
    summary, body = row.split("</summary>")
    assert "Kredyt" in summary and "<a " not in summary
    assert f'href="{INGRESS}/transactions?category={kredyt}"' in body and 'class="move"' in body
    assert f'value="{noclegi}"' in page  # kandydat do dodania
    assert "3 700,00" in page  # 6000 − 2300

    r = await client.post(
        f"/budget/fixed/{kredyt}", data={"month": MONTH, "flex_group": "flexible"}
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"{INGRESS}/budget?month={MONTH}&fixed=1#fixed"
    assert taxonomy.all_categories(conn)[kredyt].flex_group == "flexible"
    page = (await client.get(f"/budget?month={MONTH}&fixed=1")).text
    assert 'id="fixed" open' in page
    assert "„Kredyt” — grupa budżetu: elastyczne" in page
    assert "Pula automatyczna: 6\u202f000,00" in page

    await client.post("/budget/fixed/0", data={"month": MONTH, "flex_group": "fixed"})
    assert "Grupę budżetu ma tylko podkategoria" in (await client.get("/budget")).text
    await client.post(f"/budget/fixed/{noclegi}", data={"month": MONTH, "flex_group": "zle"})
    assert "Nieznana grupa budżetu" in (await client.get("/budget")).text


async def test_pool_lists_series_and_recurring_row(
    client: httpx.AsyncClient, service: Service
) -> None:
    conn = service.conn
    _seed(conn)
    slugs = taxonomy.by_slug(conn)
    prev = (date.fromisoformat(DAY) - timedelta(days=1)).replace(day=24)
    t = add(conn, "6000.00", "transfer_in", "Pensja", "FIRMA X", day=prev.isoformat())
    engine.set_manual(conn, t, slugs["wynagrodzenie"].id)
    t = add(conn, "-45.00", "transfer_out", "Abo", "STRIM Q", day=DAY)
    engine.set_manual(conn, t, slugs["spozywcze"].id)
    sid = S.insert(
        conn,
        name="Strim Q",
        direction="out",
        cadence="Q",
        conditions=Conditions(
            text=(TextCondition("counterparty_name", "equals", "STRIM Q"),), direction="out"
        ),
        expected=Decimal("300.00"),
        tolerance=Decimal("5"),
        anchor_day=int(DAY[8:]),
        status="active",
        origin="manual",
        key=None,
    )
    page = (await client.get(f"/budget?month={MONTH}")).text
    assert "Płatności cykliczne" in page and "Strim Q" in page
    assert f'href="{INGRESS}/recurring/{sid}"' in page
    assert "100,00" in page  # kwartalna ⅓ na miesiąc
    assert "<dt>Cykliczne</dt>" in page and "5\u202f900,00" in page  # 6000 − 100


async def test_add_to_fixed_from_list(client: httpx.AsyncClient, service: Service) -> None:
    conn = service.conn
    _seed(conn)
    slugs = taxonomy.by_slug(conn)
    prev = (date.fromisoformat(DAY) - timedelta(days=1)).replace(day=24)
    t = add(conn, "6000.00", "transfer_in", "Pensja", "FIRMA X", day=prev.isoformat())
    engine.set_manual(conn, t, slugs["wynagrodzenie"].id)
    t = add(conn, "-80.00", "transfer_out", "Hotel", "HOTEL Z", day=prev.replace(day=6).isoformat())
    engine.set_manual(conn, t, slugs["noclegi"].id)
    engine.recategorize(conn)
    page = (await client.get(f"/budget?month={MONTH}")).text
    assert f'action="{INGRESS}/budget/fixed"' in page and "Dodaj do stałych" in page
    r = await client.post("/budget/fixed", data={"month": MONTH, "category": slugs["noclegi"].id})
    assert r.headers["location"] == f"{INGRESS}/budget?month={MONTH}&fixed=1#fixed"
    assert taxonomy.all_categories(conn)[slugs["noclegi"].id].flex_group == "fixed"
    page = (await client.get(f"/budget?month={MONTH}&fixed=1")).text
    assert "„Noclegi” — grupa budżetu: stałe" in page and "5 920,00" in page
