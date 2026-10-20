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


# --- E2: historia ------------------------------------------------------------------------------

import json  # noqa: E402
from typing import Any  # noqa: E402

from websockets.asyncio.server import serve  # noqa: E402

from budget.storage import db  # noqa: E402


def _ms(y: int, m: int) -> int:
    return int(datetime(y, m, 1, 0, 0, tzinfo=stocks._TZ).timestamp() * 1000)


def _stats() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {
        f"{PFX}market_value_pln": [],
        f"{PFX}unvested_qty": [],
        f"{PFX}price_pln": [],
    }
    for i, m in enumerate((7, 8, 9)):
        out[f"{PFX}market_value_pln"].append({"start": _ms(2026, m), "state": 1000 + i * 100})
        out[f"{PFX}unvested_qty"].append({"start": _ms(2026, m), "mean": 100, "state": None})
        out[f"{PFX}price_pln"].append({"start": _ms(2026, m), "state": 10 + i})
    return out


class FakeHA:
    available = True

    def __init__(self, stats: dict[str, list[dict[str, Any]]] | None, fail: bool = False) -> None:
        self.stats = stats or {}
        self.fail = fail
        self.calls = 0

    async def monthly_statistics(self, *_: Any) -> dict[str, list[dict[str, Any]]]:
        self.calls += 1
        if self.fail:
            raise HAError("WS: test")
        return self.stats


def _snap(conn: sqlite3.Connection, day: str, approx: int) -> None:
    comps = [
        {
            "group": "konta",
            "name": "ROR",
            "amount": "5000",
            "liability": False,
            "note": None,
            "stale": False,
        },
        {
            "group": "kredyty",
            "name": "Kredyt",
            "amount": "2000",
            "liability": True,
            "note": None,
            "stale": False,
        },
    ]
    conn.execute(
        "INSERT INTO networth_snapshot (day, total, assets, liabilities, components_json, approx) "
        "VALUES (?, '3000', '5000', '2000', ?, ?)",
        (day, json.dumps(comps), approx),
    )


def _row(conn: sqlite3.Connection, day: str) -> sqlite3.Row:
    return conn.execute("SELECT * FROM networth_snapshot WHERE day = ?", (day,)).fetchone()


TODAY = date(2026, 10, 20)


async def test_backfill_appends_components(conn: sqlite3.Connection) -> None:
    for d in ("2026-07-31", "2026-08-31", "2026-09-30"):
        _snap(conn, d, 1)
    _snap(conn, "2026-06-30", 1)  # przed zakresem
    ha = FakeHA(_stats())
    assert await stocks.backfill_history(conn, ha, PFX, TODAY) == 3  # type: ignore[arg-type]
    r = _row(conn, "2026-08-31")
    names = [c["name"] for c in json.loads(r["components_json"])]
    assert stocks.NAME_VALUE in names and stocks.NAME_UNVESTED in names
    # 5000 + 1100 + 100 * 11 = 7200; total = 7200 - 2000
    assert Decimal(r["assets"]) == Decimal("7200.00") and Decimal(r["total"]) == Decimal("5200.00")
    assert stocks.NAME_VALUE not in _row(conn, "2026-06-30")["components_json"]
    assert db.kv_get(conn, stocks.HISTORY_FLAG) is True


async def test_backfill_leaves_exact_and_is_idempotent(conn: sqlite3.Connection) -> None:
    _snap(conn, "2026-08-31", 0)
    _snap(conn, "2026-09-30", 1)
    ha = FakeHA(_stats())
    assert await stocks.backfill_history(conn, ha, PFX, TODAY) == 1  # type: ignore[arg-type]
    assert "Akcje" not in _row(conn, "2026-08-31")["components_json"]
    assert await stocks.backfill_history(conn, ha, PFX, TODAY) == 0  # type: ignore[arg-type]
    assert ha.calls == 1
    db.kv_set(conn, stocks.HISTORY_FLAG, None)  # bez flagi: obecność składnika blokuje
    before = _row(conn, "2026-09-30")["components_json"]
    assert await stocks.backfill_history(conn, ha, PFX, TODAY) == 0  # type: ignore[arg-type]
    assert _row(conn, "2026-09-30")["components_json"] == before


async def test_backfill_ws_error_no_change_no_flag(conn: sqlite3.Connection) -> None:
    _snap(conn, "2026-09-30", 1)
    before = _row(conn, "2026-09-30")["components_json"]
    assert await stocks.backfill_history(conn, FakeHA(None, fail=True), PFX, TODAY) == 0  # type: ignore[arg-type]
    assert _row(conn, "2026-09-30")["components_json"] == before
    assert not db.kv_get(conn, stocks.HISTORY_FLAG)


async def test_backfill_no_snapshots_no_flag(conn: sqlite3.Connection) -> None:
    ha = FakeHA(_stats())
    assert await stocks.backfill_history(conn, ha, PFX, TODAY) == 0  # type: ignore[arg-type]
    assert ha.calls == 0 and not db.kv_get(conn, stocks.HISTORY_FLAG)


async def test_backfill_skips_snapshot_without_stats(conn: sqlite3.Connection) -> None:
    _snap(conn, "2026-07-31", 1)
    _snap(conn, "2026-09-30", 1)
    stats = _stats()
    for rows in stats.values():
        rows.pop(0)  # brak lipca
    assert await stocks.backfill_history(conn, FakeHA(stats), PFX, TODAY) == 1  # type: ignore[arg-type]
    assert "Akcje" not in _row(conn, "2026-07-31")["components_json"]
    assert "Akcje" in _row(conn, "2026-09-30")["components_json"]
    assert db.kv_get(conn, stocks.HISTORY_FLAG) is True


async def test_ws_client_handshake_and_statistics() -> None:
    seen: list[dict[str, Any]] = []

    async def handler(ws: Any) -> None:
        await ws.send(json.dumps({"type": "auth_required"}))
        seen.append(json.loads(await ws.recv()))
        await ws.send(json.dumps({"type": "auth_ok"}))
        req = json.loads(await ws.recv())
        seen.append(req)
        await ws.send(
            json.dumps(
                {
                    "id": req["id"],
                    "success": True,
                    "result": {"sensor.a": [{"start": 1, "state": 2}]},
                }
            )
        )

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = HAClient("tok", base_url=f"http://127.0.0.1:{port}")
        try:
            res = await client.monthly_statistics(
                ["sensor.a"], datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)
            )
        finally:
            await client.aclose()
    assert res == {"sensor.a": [{"start": 1, "state": 2}]}
    assert seen[0] == {"type": "auth", "access_token": "tok"}
    assert seen[1]["type"] == "recorder/statistics_during_period" and seen[1]["period"] == "month"


async def test_ws_client_failure_is_haerror() -> None:
    async def handler(ws: Any) -> None:
        await ws.send(json.dumps({"type": "auth_required"}))
        await ws.recv()
        await ws.send(json.dumps({"type": "auth_invalid"}))

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = HAClient("tok", base_url=f"http://127.0.0.1:{port}")
        try:
            with pytest.raises(HAError):
                await client.monthly_statistics(["x"], datetime(2026, 7, 1, tzinfo=UTC), NOW)
        finally:
            await client.aclose()
    with pytest.raises(HAError):
        await HAClient(None).monthly_statistics(["x"], NOW, NOW)


def test_group_matches_networth() -> None:
    assert stocks.GROUP == networth.INVESTMENTS


# --- poprawki z code-review ----------------------------------------------------------------------


@respx.mock
async def test_change_ignores_stocks_missing_in_reference_snapshot(
    conn: sqlite3.Connection, ha: HAClient
) -> None:
    _snap(conn, "2026-09-20", 0)  # migawka sprzed M11: bez akcji, total 3000
    mock_states(GOOD)
    await stocks.refresh(conn, ha, PFX, NOW)
    ch = networth.change(conn, Decimal("5500"), DAY, 30)  # dziś 3500 + akcje 1000 + 1000
    assert ch is not None and ch.delta == Decimal("500")  # 5500 − 2000 (akcje) − 3000


@respx.mock
async def test_empty_prefix_clears_previous_entry(conn: sqlite3.Connection, ha: HAClient) -> None:
    mock_states(GOOD)
    await stocks.refresh(conn, ha, PFX, NOW)
    await stocks.refresh(conn, ha, "", NOW + timedelta(days=1))
    assert stocks.load(conn) is None


@respx.mock
async def test_unavailable_vest_date_keeps_previous_date(
    conn: sqlite3.Connection, ha: HAClient
) -> None:
    mock_states(GOOD)
    await stocks.refresh(conn, ha, PFX, NOW)
    mock_states({**GOOD, "next_vest_date": "unavailable"})
    await stocks.refresh(conn, ha, PFX, NOW + timedelta(days=1))
    held = stocks.load(conn)
    assert held is not None and held.next_vest == date(2026, 12, 1)
    assert held.next_vest_qty == Decimal("25")


@respx.mock
async def test_stale_after_stocks_stale_days(conn: sqlite3.Connection, ha: HAClient) -> None:
    mock_states(GOOD)
    await stocks.refresh(conn, ha, PFX, NOW)
    later = DAY + timedelta(days=stocks.STALE_DAYS + 1)
    comps = [c for c in networth.compute(conn, later).components if "Akcje" in c.name]
    assert len(comps) == 2 and all(c.stale for c in comps)
