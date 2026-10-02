"""Panel M4c/2: karta „Podpowiedzi AI” na Status, przebieg na żądanie, pomiar trafności."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from budget.categorize import engine as categorize
from budget.ha_client import HAClient
from budget.service import Service
from budget.settings import Settings
from budget.storage import db
from budget.suggest import client as ai_client
from budget.suggest import engine

from .test_categorize_engine import add, sid
from .test_web import _client

__all__ = ["service"]
from .test_web import service

ROUTER = "http://router:3003/v1"


@pytest.fixture
def ai_service(tmp_path: Path) -> Service:
    settings = Settings(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        ai_base_url=ROUTER,
        ai_api_key="sekret",
        ai_daily_calls=3,
    )
    conn = db.connect(":memory:")
    conn.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', ?)",
        (db.now_iso(),),
    )
    add(conn, "-30.00", "card", "QWERTY 12 XYZ POL 2026-09-01", day="2026-09-01")
    categorize.recategorize(conn)
    return Service(settings, conn, HAClient(None), tz=ZoneInfo("Europe/Warsaw"))


@pytest.fixture
async def ai(ai_service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(ai_service) as c:
        yield c


@pytest.fixture(autouse=True)
def no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_client, "RETRY_DELAYS", (0.0, 0.0))


def _answer(cid: int) -> httpx.Response:
    content = {"items": [{"i": 0, "category_id": cid, "confidence": 0.9}]}
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps(content)}}],
            "usage": {"total_tokens": 9},
        },
    )


async def test_status_card_disabled(service: Service) -> None:
    async with _client(service) as c:
        page = (await c.get("/")).text
    assert "Podpowiedzi AI" in page and "Wyłączone" in page and "Zmierz trafność" not in page
    async with _client(service) as c:
        r = await c.post("/ai/run", follow_redirects=False)
    assert r.status_code == 303


@respx.mock
async def test_run_now_and_status(ai: httpx.AsyncClient, ai_service: Service) -> None:
    leaf = sid(ai_service.conn, "restauracje")
    route = respx.post(f"{ROUTER}/chat/completions").mock(return_value=_answer(leaf))
    page = (await ai.get("/")).text
    assert "Podpowiedz teraz" in page and "1 sprzedawców w kolejce" in page
    assert (await ai.post("/ai/run")).status_code == 303
    r = await ai.get("/")
    assert "wywołań 1, zapisanych 1, czeka 0" in r.text
    assert "1 czeka na decyzję" in r.text and "1 / 3" in r.text
    assert route.call_count == 1
    assert "sekret" not in r.text


@respx.mock
async def test_run_error_is_shown(ai: httpx.AsyncClient) -> None:
    respx.post(f"{ROUTER}/chat/completions").mock(return_value=httpx.Response(401, text="nope"))
    await ai.post("/ai/run")
    r = await ai.get("/")
    assert "HTTP 401" in r.text and "Ostatni błąd" in r.text


@respx.mock
async def test_eval_shows_accuracy(ai: httpx.AsyncClient, ai_service: Service) -> None:
    conn = ai_service.conn
    lidl = add(conn, "-50.00", "card", "LIDL UL. X XYZ POL 2026-09-01")
    categorize.recategorize(conn)
    respx.post(f"{ROUTER}/chat/completions").mock(return_value=_answer(sid(conn, "spozywcze")))
    await ai.post("/ai/eval")
    r = await ai.get("/")
    assert "Pomiar trafności: 1 sprzedawców" in r.text
    assert "Trafność" in r.text and "100%" in r.text
    assert engine.usage(conn, ai_service.now().date())["calls"] == 1
    assert lidl


async def test_suggest_later_runs_in_background(ai_service: Service) -> None:
    calls = []

    async def fake() -> engine.RunResult:
        calls.append(1)
        return engine.RunResult()

    ai_service.suggest = fake  # type: ignore[method-assign]
    ai_service.suggest_later()
    ai_service.suggest_later()  # drugi, gdy pierwszy trwa — pominięty
    assert ai_service._ai_task is not None
    await ai_service._ai_task
    assert calls == [1]
