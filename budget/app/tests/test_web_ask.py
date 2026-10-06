"""Panel M12: zakładka „Zapytaj” — bez routera AI, odpowiedź htmx, przykłady, link do transakcji."""

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

from .test_ask_engine import PLAN
from .test_categorize_engine import add
from .test_web import _client

__all__ = ["service"]
from .test_web import service

ROUTER = "http://router:3003/v1"
HX = {"HX-Request": "true"}


@pytest.fixture
def ai_service(tmp_path: Path) -> Service:
    settings = Settings(config_dir=tmp_path / "c", data_dir=tmp_path / "d", ai_base_url=ROUTER)
    conn = db.connect(":memory:")
    conn.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', ?)",
        (db.now_iso(),),
    )
    add(conn, "-200.00", "transfer_out", "Przelew A", "JXN QWERTOWSKI", day="2026-09-03")
    add(conn, "-50.00", "card", "QWERTYSHOP", day="2026-09-05")
    categorize.recategorize(conn)
    return Service(settings, conn, HAClient(None), tz=ZoneInfo("Europe/Warsaw"))


@pytest.fixture
async def ai(ai_service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(ai_service) as c:
        yield c


def _reply(content: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": json.dumps(content)}}], "usage": {}}
    )


async def test_disabled_without_router(service: Service) -> None:
    async with _client(service) as c:
        page = (await c.get("/ask")).text
    assert "ai_base_url" in page and "<textarea" not in page
    assert '/ask" class=' in page  # zakładka w nawigacji


@respx.mock
async def test_ask_htmx_partial(ai: httpx.AsyncClient) -> None:
    route = respx.post(f"{ROUTER}/chat/completions").mock(
        side_effect=[_reply(PLAN), _reply({"answer": "Najwięcej: [O1] (200,00 zł)."})]
    )
    page = (await ai.get("/ask")).text
    assert "<textarea" in page and "Pozostało pytań dziś: 20" in page
    r = await ai.post("/ask", data={"q": "Komu płacimy najwięcej?"}, headers=HX)
    assert r.status_code == 200 and "<html" not in r.text
    assert "Jxn Qwertowski" in r.text and "[O1]" not in r.text  # nazwa podmieniona lokalnie
    assert "Qwertyshop" in r.text or "QWERTYSHOP" in r.text.upper()
    assert "Jak policzono" in r.text and "Pozostało pytań dziś: 19" in r.text
    assert "transactions?date_from=2026-09-01&amp;date_to=2026-09-30" in r.text
    sent = [json.loads(c.request.content)["messages"][0]["content"] for c in route.calls]
    assert all("qwertowski" not in s.lower() for s in sent)
    page = (await ai.get("/ask")).text
    assert "Ostatnie pytania" in page and "Komu płacimy najwięcej?" in page


@respx.mock
async def test_example_wins_over_textarea(ai: httpx.AsyncClient) -> None:
    route = respx.post(f"{ROUTER}/chat/completions").mock(
        return_value=_reply({**PLAN, "unsupported": "brak sald"})
    )
    r = await ai.post("/ask", data={"q": "stare", "example": "Przykład X"}, headers=HX)
    assert "Nie umiem odpowiedzieć" in r.text and "brak sald" in r.text
    assert "Przykład X" in json.loads(route.calls[0].request.content)["messages"][0]["content"]
