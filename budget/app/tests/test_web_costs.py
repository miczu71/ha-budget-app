"""Ekran „Koszty banku” (M23 E4)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, datetime
from decimal import Decimal

import httpx
import pytest

from budget import fx
from budget.service import Service
from budget.storage.db import now_iso

from .test_categorize_engine import add
from .test_web import _client, service

__all__ = ["service"]


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    service.now = lambda: datetime(2026, 10, 13, 9, 0, tzinfo=service.tz)  # type: ignore[method-assign]
    async with _client(service) as c:
        yield c


def seed(service: Service) -> None:
    conn = service.conn
    conn.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (2, 'card', 'PLN', ?)",
        (now_iso(),),
    )
    conn.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', ?)",
        (now_iso(),),
    )
    fx.store(conn, "EUR", {date(2026, 9, 4): Decimal("4.0000")})
    add(
        conn,
        "-102.00",
        "card",
        "SKLEP X",
        day="2026-09-07",
        account=2,
        orig_amount="-25.00",
        orig_currency="EUR",
    )
    add(conn, "-7.00", "fee", "OPLATA ZA KARTE", day="2026-08-05")


async def test_empty_state_explains_where_data_comes_from(client: httpx.AsyncClient) -> None:
    page = (await client.get("/costs")).text
    assert "Koszty banku" in page
    assert "Import CSV" in page


async def test_year_totals_months_and_rows(service: Service, client: httpx.AsyncClient) -> None:
    seed(service)
    resp = await client.get("/costs?year=2026")
    assert resp.status_code == 200
    page = resp.text
    assert "9,00" in page  # razem: 2,00 przewalutowanie + 7,00 opłaty
    assert "SKLEP X" in page and "25,00\xa0€" in page and "4,0000" in page
    assert "OPLATA ZA KARTE" in page
    assert "wrzesień" in page.lower()
    assert "/costs?year=2025" in page  # poprzedni rok
    assert "/costs?year=2027" not in page  # przyszłego roku nie ma
