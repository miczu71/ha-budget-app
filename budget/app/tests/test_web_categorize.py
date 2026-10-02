"""Panel M4a: Wydatki, kategorie w Transakcjach, Reguły (edytor + podgląd), Słownik, Kategorie."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from datetime import date

import httpx
import pytest

from budget import __version__
from budget.categorize import engine, rules, taxonomy
from budget.service import Service
from budget.storage.db import now_iso

from .test_categorize_engine import add
from .test_web import INGRESS, _client

__all__ = ["service"]
from .test_web import service

TODAY = date.today()
DAY = TODAY.replace(day=1).isoformat()


def _seed(conn: sqlite3.Connection) -> dict[str, int]:
    conn.execute(
        "INSERT INTO account (id, kind, currency, display_name, created_at) "
        "VALUES (1, 'current', 'PLN', 'Rachunek', ?)",
        (now_iso(),),
    )
    ids = {
        "lidl": add(conn, "-50.00", "card", "LIDL UL. X XYZ POL", day=DAY),
        "kebab": add(conn, "-30.00", "card", "KEBAB ABC XYZ POL", day=DAY),
        "orlen": add(conn, "-200.00", "card", "ORLEN STACJA 1 XYZ", day=DAY),
        "salary": add(conn, "5000.00", "transfer_in", "Pensja", "FIRMA SP Z O O", day=DAY),
        "own": add(conn, "-700.00", "card_repayment", "", None, day=DAY, transfer_group="t1"),
    }
    engine.recategorize(conn)
    return ids


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


async def test_nav_and_empty_pages(client: httpx.AsyncClient) -> None:
    for path in ("/spending", "/rules", "/rules/new", "/dictionary", "/categories"):
        r = await client.get(path)
        assert r.status_code == 200, path
        assert r.headers["cache-control"] == "no-store"
    page = (await client.get("/")).text
    assert f'href="{INGRESS}/spending"' in page and f'href="{INGRESS}/rules"' in page
    assert "brak wydatków" in (await client.get("/spending")).text


async def test_spending_page(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)
    page = (await client.get("/spending")).text
    assert "Jedzenie" in page and "Transport" in page
    assert "Nieskategoryzowane" not in page  # wszystkie wydatki mają kategorię ze słownika
    assert "280,00" in page  # 50 + 30 + 200
    assert "przypisz kategorie" not in page
    assert f"{INGRESS}/transactions?category=2&date_from={DAY}" in page
    assert "bez kategorii" in page  # pensja bez reguły
    # przyszły miesiąc → bieżący; brak strzałki „dalej”
    future = (await client.get("/spending?month=2999-01")).text
    assert 'aria-label="następny miesiąc"' not in future


async def test_transactions_filters_and_manual_category(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _seed(service.conn)
    page = (await client.get("/transactions?category=none")).text
    assert "Firma Sp Z O O" in page and "Lidl" not in page
    assert "przelew własny" not in page  # przelew wewnętrzny nie jest „bez kategorii”
    food = taxonomy.by_slug(service.conn)["jedzenie"].id
    page = (await client.get(f"/transactions?category={food}&direction=out")).text
    assert "Lidl" in page and "Firma" not in page

    form = (await client.get(f"/transactions/{ids['kebab']}/category")).text
    assert "<select" in form and "automatycznie" in form
    leaf = taxonomy.by_slug(service.conn)["restauracje"].id
    r = await client.post(f"/transactions/{ids['kebab']}/category", data={"category_id": str(leaf)})
    assert r.status_code == 200
    assert "Restauracje i kawiarnie" in r.text and "ręczna" in r.text
    assert f"{INGRESS}/rules/new?txn={ids['kebab']}" in r.text
    r = await client.post(f"/transactions/{ids['kebab']}/category", data={"category_id": ""})
    assert "ręczna" not in r.text
    r = await client.post(f"/transactions/{ids['own']}/category", data={"category_id": str(leaf)})
    assert "przelew własny" in r.text


async def test_rule_preview_save_and_actions(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    salary = taxonomy.by_slug(conn)["wynagrodzenie"].id
    form = {
        "field_0": "merchant",
        "op_0": "contains",
        "value_0": "firma",
        "category_id": str(salary),
        "direction": "in",
    }
    r = await client.post("/rules/preview", data=form)
    assert "Pasuje: 1" in r.text and "Firma Sp Z O O" in r.text
    r = await client.post("/rules/preview", data={**form, "value_0": ""})
    assert "co najmniej jednego" in r.text

    r = await client.post("/rules/save", data={**form, "rename": "Pensja"})
    assert r.status_code == 303 and r.headers["location"] == f"{INGRESS}/rules"
    page = (await client.get("/rules")).text
    assert "Reguła zapisana; zaktualizowane transakcje: 1" in page
    assert "sprzedawca / odbiorca zawiera „firma”" in page
    assert (
        conn.execute("SELECT merchant FROM txn WHERE id = ?", (ids["salary"],)).fetchone()[0]
        == "Pensja"
    )

    rid = rules.all_rules(conn)[0].id
    assert (await client.get(f"/rules/{rid}")).status_code == 200
    await client.post(f"/rules/{rid}/toggle")
    assert (
        conn.execute("SELECT category_id FROM txn WHERE id = ?", (ids["salary"],)).fetchone()[0]
        is None
    )
    await client.post(f"/rules/{rid}/move", data={"step": "-1"})
    await client.post(f"/rules/{rid}/delete")
    assert rules.all_rules(conn) == []
    r = await client.get("/rules/999")
    assert r.status_code == 303


async def test_rule_save_invalid_keeps_form(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)
    r = await client.post(
        "/rules/save", data={"field_0": "merchant", "op_0": "contains", "value_0": "x"}
    )
    assert r.status_code == 200 and "Wybierz podkategorię" in r.text
    r = await client.post(
        "/rules/save",
        data={"value_0": "x", "category_id": "110", "amount_min": "abc"},
    )
    assert "Niepoprawna kwota" in r.text


async def test_new_rule_prefilled_from_transaction(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _seed(service.conn)
    page = (await client.get(f"/rules/new?txn={ids['lidl']}")).text
    assert 'value="Lidl"' in page
    assert '<option value="equals" selected>' in page


async def test_dictionary_and_categories(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)
    page = (await client.get("/dictionary?q=lidl")).text
    assert "Lidl" in page and "Biedronka" not in page
    page = (await client.get("/dictionary")).text
    assert "(słowa ogólne)" in page
    assert f"v{__version__}" in page  # wersja słownika nie przesłania wersji add-onu

    r = await client.post("/categories/add", data={"parent_id": "4", "name": "Rower"})
    assert r.status_code == 303
    assert "Dodano podkategorię" in (await client.get("/categories")).text
    r = await client.post("/categories/add", data={"parent_id": "4", "name": "rower"})
    assert "już istnieje" in (await client.get("/categories")).text
    await client.post("/categories/110/rename", data={"name": "Zakupy spożywcze"})
    assert "Zakupy spożywcze" in (await client.get("/categories")).text


async def test_rule_from_correction_takes_over_manual(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    gifts = taxonomy.by_slug(conn)["prezenty"].id
    await client.post(f"/transactions/{ids['salary']}/category", data={"category_id": str(gifts)})
    page = (await client.get(f"/rules/new?txn={ids['salary']}")).text
    assert f'name="txn" value="{ids["salary"]}"' in page
    form = {
        "field_0": "merchant",
        "op_0": "equals",
        "value_0": "Firma Sp Z O O",
        "category_id": str(gifts),
        "txn": str(ids["salary"]),
    }
    r = await client.post("/rules/preview", data=form)
    assert "Dostanie tę kategorię: <strong>1</strong>" in r.text and "Ręcznie" not in r.text
    await client.post("/rules/save", data=form)
    row = conn.execute("SELECT category_source FROM txn WHERE id = ?", (ids["salary"],)).fetchone()
    assert row[0] == "rule"
