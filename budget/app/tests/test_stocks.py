"""Akcje pracownicze (M11 E1): odczyt encji do `kv`, składniki majątku netto."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import respx

from budget import networth, stocks
from budget.ha_client import HAClient, HAError

from .test_categorize_engine import conn

__all__ = ["conn"]

SUP = "http://supervisor"
PFX = "sensor.test_tracker_"
NOW = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
DAY = date(2026, 10, 20)


@pytest.fixture
async def ha() -> AsyncIterator[HAClient]:
    async with httpx.AsyncClient() as http:
        yield HAClient("tok", http=http)


def mock_states(values: dict[str, str], qty: str = "25") -> None:
    for name, state in values.items():
        attrs = {"next_vest_qty": qty} if name == "next_vest_date" else {}
        respx.get(f"{SUP}/core/api/states/{PFX}{name}").mock(
            return_value=httpx.Response(200, json={"state": state, "attributes": attrs})
        )


GOOD = {
    "market_value_pln": "1000.00",
    "price_pln": "10.00",
    "unvested_qty": "100",
    "next_vest_date": "2026-12-01",
}


@respx.mock
async def test_get_state_404_is_none_and_other_errors_raise(ha: HAClient) -> None:
    respx.get(f"{SUP}/core/api/states/sensor.a").mock(return_value=httpx.Response(404))
    respx.get(f"{SUP}/core/api/states/sensor.b").mock(return_value=httpx.Response(500))
    assert await ha.get_state("sensor.a") is None
    with pytest.raises(HAError):
        await ha.get_state("sensor.b")


@respx.mock
async def test_refresh_stores_and_load(conn: sqlite3.Connection, ha: HAClient) -> None:
    mock_states(GOOD)
    await stocks.refresh(conn, ha, PFX, NOW)
    held = stocks.load(conn)
    assert held is not None
    assert held.market_value == Decimal("1000.00")
    assert held.unvested_qty == Decimal("100")
    assert held.price == Decimal("10.00")
    assert held.next_vest == date(2026, 12, 1)
    assert held.next_vest_qty == Decimal("25")
    assert held.fetched_at == NOW


@respx.mock
async def test_unavailable_keeps_previous(conn: sqlite3.Connection, ha: HAClient) -> None:
    mock_states(GOOD)
    await stocks.refresh(conn, ha, PFX, NOW)
    mock_states({**GOOD, "price_pln": "unavailable"})
    await stocks.refresh(conn, ha, PFX, NOW + timedelta(days=1))
    held = stocks.load(conn)
    assert held is not None and held.fetched_at == NOW and held.price == Decimal("10.00")


@respx.mock
async def test_missing_entity_keeps_previous(conn: sqlite3.Connection, ha: HAClient) -> None:
    mock_states(GOOD)
    await stocks.refresh(conn, ha, PFX, NOW)
    respx.get(f"{SUP}/core/api/states/{PFX}unvested_qty").mock(return_value=httpx.Response(404))
    await stocks.refresh(conn, ha, PFX, NOW + timedelta(days=1))
    held = stocks.load(conn)
    assert held is not None and held.fetched_at == NOW


async def test_empty_prefix_does_nothing(conn: sqlite3.Connection, ha: HAClient) -> None:
    await stocks.refresh(conn, ha, "", NOW)  # bez mocka: gdyby wołał HTTP, test by padł
    assert stocks.load(conn) is None


@respx.mock
async def test_components_sum_and_note(conn: sqlite3.Connection, ha: HAClient) -> None:
    mock_states(GOOD)
    await stocks.refresh(conn, ha, PFX, NOW)
    comps = {c.name: c for c in networth.compute(conn, DAY).components}
    own = comps["Akcje Nokia"]
    unvested = comps["Akcje Nokia — niezawiązane"]
    assert own.amount == Decimal("1000.00")
    assert unvested.amount == Decimal("1000.00")  # 100 akcji po 10,00 zł
    assert own.group == unvested.group == networth.INVESTMENTS
    assert unvested.note == "vesting 01.12.2026: 25 akcji"
    assert not own.stale and not unvested.stale


@respx.mock
async def test_past_has_no_stocks(conn: sqlite3.Connection, ha: HAClient) -> None:
    mock_states(GOOD)
    await stocks.refresh(conn, ha, PFX, NOW)
    nw = networth.compute(conn, DAY - timedelta(days=30), past=True)
    assert not [c for c in nw.components if "Akcje" in c.name]


@respx.mock
async def test_stale_after_double_stale_days(conn: sqlite3.Connection, ha: HAClient) -> None:
    mock_states(GOOD)
    await stocks.refresh(conn, ha, PFX, NOW)
    later = DAY + timedelta(days=2 * networth.STALE_DAYS)
    comps = [c for c in networth.compute(conn, later).components if "Akcje" in c.name]
    assert len(comps) == 2 and all(c.stale for c in comps)
