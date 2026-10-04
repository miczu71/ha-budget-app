"""Świeżość encji: odświeżenie po zapisie w panelu (debounce) i tuż po północy."""

from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from budget import service as service_mod
from budget.service import Service, next_midnight

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
