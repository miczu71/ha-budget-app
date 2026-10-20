"""Świeżość encji: odświeżenie po zapisie w panelu (debounce) i tuż po północy."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest

from budget import service as service_mod
from budget.service import Service, next_midnight

from .test_categorize_engine import add
from .test_web import _client, service

__all__ = ["service"]

WAW = ZoneInfo("Europe/Warsaw")


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 4, 13, 0, tzinfo=WAW), datetime(2026, 10, 5, 0, 0, 5, tzinfo=WAW)),
        (datetime(2026, 10, 31, 23, 59, tzinfo=WAW), datetime(2026, 11, 1, 0, 0, 5, tzinfo=WAW)),
        (datetime(2026, 10, 5, 0, 0, 5, tzinfo=WAW), datetime(2026, 10, 6, 0, 0, 5, tzinfo=WAW)),
    ],
)
def test_next_midnight(now: datetime, expected: datetime) -> None:
    assert next_midnight(now) == expected


def test_next_midnight_across_dst_in_real_seconds() -> None:
    now = datetime(2027, 3, 28, 1, 0, tzinfo=WAW)  # o 2:00 zegar przeskakuje na 3:00
    at = next_midnight(now)
    assert at == datetime(2027, 3, 29, 0, 0, 5, tzinfo=WAW)
    assert at.timestamp() - now.timestamp() == 22 * 3600 + 5


async def test_refresh_soon_debounces(service: Service, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    async def fake_refresh() -> None:
        calls.append(1)

    monkeypatch.setattr(service_mod, "REFRESH_DEBOUNCE", 0.01)
    monkeypatch.setattr(service, "refresh", fake_refresh)
    service.refresh_soon()
    service.refresh_soon()
    await asyncio.sleep(0.05)
    assert calls == [1]
    service.refresh_soon()  # po zakończeniu poprzedniego — kolejne odświeżenie
    await asyncio.sleep(0.05)
    assert calls == [1, 1]


async def test_panel_post_schedules_refresh(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(service, "refresh_soon", lambda: calls.append("x"))
    async with _client(service) as client:
        await client.get("/budget")
        assert calls == []
        r = await client.post("/budget/amount", data={"month": "2026-09", "amount": "1000"})
        assert r.status_code < 400 and calls == ["x"]
        r = await client.post("/nie-ma-takiej-trasy", data={})
        assert r.status_code >= 400 and calls == ["x"]


class _DummyEB:
    async def __aenter__(self) -> _DummyEB:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("[Errno -3] Try again"),  # DNS — to nie OSError
        httpx.ReadTimeout("timeout"),
        RuntimeError("cokolwiek"),
    ],
)
async def test_session_check_survives_errors(
    service: Service, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    refreshed: list[int] = []

    async def failing_status(*_: object) -> None:
        raise error

    async def fake_refresh() -> None:
        refreshed.append(1)

    monkeypatch.setattr(service, "missing_config", lambda: [])
    monkeypatch.setattr(service, "eb_client", lambda: _DummyEB())
    monkeypatch.setattr(service_mod.sessions, "current", lambda _conn: object())
    monkeypatch.setattr(service_mod.sessions, "refresh_status", failing_status)
    monkeypatch.setattr(service, "refresh", fake_refresh)
    await service.session_check()  # nie rzuca — pętla session_watch żyje dalej
    assert refreshed == [1]  # encje odświeżone mimo błędu sprawdzenia zgody


async def test_session_check_survives_refresh_error(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken_refresh() -> None:
        raise RuntimeError("MQTT")

    monkeypatch.setattr(service, "missing_config", lambda: ["klucz"])
    monkeypatch.setattr(service, "refresh", broken_refresh)
    await service.session_check()


async def test_record_networth_backfills_once_and_survives_nbp_failure(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    from budget import fx

    async def boom(cur: str, start: date, end: date) -> dict[date, Decimal]:
        raise httpx.ConnectError("brak sieci")

    monkeypatch.setattr(fx, "fetch", boom)
    conn = service.conn
    conn.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', 'x')"
    )
    conn.execute(
        "INSERT INTO balance_snapshot (account_id, balance_type, amount, currency, fetched_at) "
        "VALUES (1, 'ITAV', '500.00', 'PLN', '2026-01-01T06:00:00+00:00')"
    )
    add(conn, "-20", day="2026-01-10")
    await service.record_networth()
    await service.record_networth()
    rows = conn.execute("SELECT day, approx FROM networth_snapshot ORDER BY day").fetchall()
    today = service.now().date().isoformat()
    assert rows[-1]["day"] == today and rows[-1]["approx"] == 0
    assert rows[0]["day"] == "2026-01-31" and rows[0]["approx"] == 1
    assert len({r["day"] for r in rows}) == len(rows)
