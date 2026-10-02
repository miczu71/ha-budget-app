"""Wyszukiwanie na żywo (0.6.1): Reguły, Słownik, Transakcje — jedno dopasowanie po `fold`."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest

from budget.categorize import engine, rules
from budget.categorize.rules import Conditions, Rule, TextCondition
from budget.service import Service
from budget.storage.db import now_iso

from .test_categorize_engine import add
from .test_web import INGRESS, _client

__all__ = ["service"]
from .test_web import service

HX = {"HX-Request": "true"}


def _seed(conn: sqlite3.Connection) -> dict[str, int]:
    conn.execute(
        "INSERT INTO account (id, kind, currency, display_name, created_at) "
        "VALUES (1, 'current', 'PLN', 'Rachunek', ?)",
        (now_iso(),),
    )
    ids = {
        "rent": add(conn, "-900.00", "transfer_out", "Czynsz za miesiąc", "SPÓŁDZIELNIA QWĘRTÓŚ"),
        "pct": add(conn, "-10.00", "transfer_out", "Zwrot 100% za bilet_ulgowy", "Jxna Qwertowska"),
        "shop": add(conn, "-50.00", "card", "LIDL UL. X XYZ POL"),
    }
    for value, category, op in (("czynsz", 120, "contains"), ("Qwertowska", 102, "equals")):
        rules.save(
            conn,
            Rule(
                None,
                category,
                Conditions(
                    text=(
                        TextCondition("description" if op == "contains" else "merchant", op, value),
                    ),
                    direction="out",
                ),
            ),
        )
    rules.save(
        conn,
        Rule(
            None,
            111,
            Conditions(
                text=(TextCondition("merchant", "contains", "kebab"),), amount_min=Decimal("5")
            ),
        ),
    )
    engine.recategorize(conn)
    return ids


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


def _rows(page: str) -> int:
    return page.count('class="rule-row')


async def test_rules_search(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)
    page = (await client.get("/rules")).text
    assert _rows(page) == 3 and 'type="search"' in page and "wyżej" in page
    page = (await client.get("/rules?q=CZYN")).text  # wartość warunku, wielkość liter
    assert _rows(page) == 1 and "„czynsz”" in page and "1 z 3" in page
    assert "wyżej" not in page and "Kolejność zmieniasz bez filtra" in page
    page = (await client.get("/rules?q=jedzenie")).text  # kategoria główna
    assert _rows(page) == 1 and "„kebab”" in page
    page = (await client.get("/rules?q=wplywy qwert")).text  # bez ogonków, dwa słowa
    assert _rows(page) == 1 and "Qwertowska" in page
    page = (await client.get("/rules?q=nic+takiego")).text
    assert _rows(page) == 0 and "Nic nie pasuje do „nic takiego”" in page

    r = await client.get("/rules?q=czynsz", headers=HX)  # htmx: blok wyników jest w odpowiedzi
    assert 'id="rules-list"' in r.text

    rid = next(x.id for x in rules.all_rules(service.conn) if x.category_id == 120)
    r = await client.post(f"/rules/{rid}/toggle", data={"q": "czyn sz"})
    assert r.headers["location"] == f"{INGRESS}/rules?q=czyn%20sz"
    r = await client.post(f"/rules/{rid}/delete", data={"q": ""})
    assert r.headers["location"] == f"{INGRESS}/rules"


async def test_dictionary_search_folds(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)
    page = (await client.get("/dictionary?q=zabka")).text
    assert "Żabka" in page and "Lidl" not in page
    page = (await client.get("/dictionary?q=ŻABKA")).text
    assert "Żabka" in page
    page = (await client.get("/dictionary?q=xyzzy")).text
    assert "Nic nie pasuje do „xyzzy”" in page
    assert 'id="dict-list"' in (await client.get("/dictionary?q=lidl", headers=HX)).text


async def test_transactions_search_folds(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)
    page = (await client.get("/transactions?q=qwertos")).text  # „QWĘRTÓŚ” bez ogonków
    assert "Czynsz za miesiąc" in page and "Lidl" not in page
    page = (await client.get("/transactions?q=miesiac+czynsz")).text  # dwa słowa, odwrotnie
    assert "Czynsz za miesiąc" in page
    page = (await client.get("/transactions?q=czynsz+lidl")).text  # AND, nie OR
    assert "Czynsz za miesiąc" not in page and "Nic nie pasuje" in page
    page = (await client.get("/transactions?q=100%25")).text  # % dosłownie
    assert "bilet_ulgowy" in page and "Czynsz" not in page
    page = (await client.get("/transactions?q=t_u")).text  # _ dosłownie
    assert "bilet_ulgowy" in page and "Czynsz" not in page
    # formularz wysyła wszystkie pola; „wszystkie konta” = pusty parametr (wcześniej 422)
    r = await client.get(
        "/transactions?account=&date_from=&date_to=&category=&direction=&kind=&q=czynsz"
    )
    assert r.status_code == 200 and "Czynsz za miesiąc" in r.text
    r = await client.get("/transactions?q=lidl", headers=HX)
    assert 'id="tx-results"' in r.text
