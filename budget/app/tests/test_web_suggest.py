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
from budget.categorize import rules
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
    content = {"items": [{"i": 0, "candidates": [{"category_id": cid, "confidence": 0.9}]}]}
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps(content)}}],
            "usage": {"total_tokens": 9},
        },
    )


async def test_status_card_disabled(service: Service) -> None:
    async with _client(service) as c:
        page = (await c.get("/status")).text
    assert "Podpowiedzi AI" in page and "Wyłączone" in page and "Zmierz trafność" not in page
    async with _client(service) as c:
        r = await c.post("/ai/run", follow_redirects=False)
    assert r.status_code == 303


@respx.mock
async def test_run_now_and_status(ai: httpx.AsyncClient, ai_service: Service) -> None:
    leaf = sid(ai_service.conn, "restauracje")
    route = respx.post(f"{ROUTER}/chat/completions").mock(return_value=_answer(leaf))
    page = (await ai.get("/status")).text
    assert "Podpowiedz teraz" in page and "1 sprzedawców w kolejce" in page
    assert (await ai.post("/ai/run")).status_code == 303
    r = await ai.get("/status")
    assert "wywołań 1, zapisanych 1, czeka 0" in r.text
    assert "1 czeka na decyzję" in r.text and "1 / 3" in r.text
    assert route.call_count == 1
    assert "sekret" not in r.text


@respx.mock
async def test_run_error_is_shown(ai: httpx.AsyncClient) -> None:
    respx.post(f"{ROUTER}/chat/completions").mock(return_value=httpx.Response(401, text="nope"))
    await ai.post("/ai/run")
    r = await ai.get("/status")
    assert "odrzucił klucz" in r.text and "Ostatni błąd" in r.text and "nope" not in r.text


@respx.mock
async def test_eval_shows_accuracy(ai: httpx.AsyncClient, ai_service: Service) -> None:
    conn = ai_service.conn
    lidl = add(conn, "-50.00", "card", "LIDL UL. X XYZ POL 2026-09-01")
    categorize.recategorize(conn)
    respx.post(f"{ROUTER}/chat/completions").mock(return_value=_answer(sid(conn, "spozywcze")))
    await ai.post("/ai/eval")
    r = await ai.get("/status")
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


def _suggest(service: Service, merchant: str, direction: str, *slugs: str) -> list[int]:
    ids = [sid(service.conn, s) for s in slugs]
    cands = [[cid, 0.9 - n / 10] for n, cid in enumerate(ids)]
    service.conn.execute(
        "INSERT INTO suggestion (merchant, direction, category_id, confidence, candidates, model, "
        "created_at) VALUES (?, ?, ?, ?, ?, 'm', ?)",
        (merchant, direction, ids[0], cands[0][1], json.dumps(cands), db.now_iso()),
    )
    return ids


GROUP = {"kind": "merchant", "value": "Qwerty", "direction": "out", "currency": "PLN", "gid": "m1"}


async def test_queue_chips_pick_and_assign(ai: httpx.AsyncClient, ai_service: Service) -> None:
    r, s, o = _suggest(ai_service, "Qwerty", "out", "restauracje", "spozywcze", "ogrod")
    page = (await ai.get("/review")).text
    assert "Podpowiedz teraz (AI)" in page
    assert page.count('class="chip ') == 3 and f"pick={r}" in page and f"pick={o}" in page
    li = (await ai.get("/review/item", params={**GROUP, "pick": str(s)})).text
    assert "<details open" in li and f'value="{s}" selected' in li
    assert "Kategoria ręczna" in li and "Spożywcze" in li  # gotowy podgląd (domyślnie bez reguły)
    assert 'class="chip on"' in li  # wybrana propozycja wyróżniona
    # zapis inną kategorią → podpowiedź odrzucona; chipów już nie ma
    txn = ai_service.conn.execute("SELECT id FROM txn").fetchone()["id"]
    await ai.post(
        "/review/assign",
        data={**GROUP, "category_id": str(sid(ai_service.conn, "kultura")), "txn": [str(txn)]},
    )
    status = ai_service.conn.execute("SELECT status FROM suggestion").fetchone()["status"]
    assert status == "rejected"
    assert "1 odrzuconych" in (await ai.get("/status")).text


async def test_assign_with_candidate_is_accepted(
    ai: httpx.AsyncClient, ai_service: Service
) -> None:
    _, s, _ = _suggest(ai_service, "Qwerty", "out", "restauracje", "spozywcze", "ogrod")
    txn = ai_service.conn.execute("SELECT id FROM txn").fetchone()["id"]
    await ai.post("/review/assign", data={**GROUP, "category_id": str(s), "txn": [str(txn)]})
    assert (
        ai_service.conn.execute("SELECT status FROM suggestion").fetchone()["status"] == "accepted"
    )


async def test_chips_hidden_when_ai_disabled(service: Service) -> None:
    service.conn.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', ?)",
        (db.now_iso(),),
    )
    add(service.conn, "-30.00", "card", "QWERTY 12 XYZ POL 2026-09-01", day="2026-09-01")
    categorize.recategorize(service.conn)
    _suggest(service, "Qwerty", "out", "restauracje")
    async with _client(service) as c:
        page = (await c.get("/review")).text
    assert "Qwerty" in page and 'class="chip' not in page and "Podpowiedz teraz" not in page


async def test_transaction_form_chips(ai: httpx.AsyncClient, ai_service: Service) -> None:
    r, s = _suggest(ai_service, "Qwerty", "out", "restauracje", "spozywcze")
    txn = ai_service.conn.execute("SELECT id FROM txn").fetchone()["id"]
    form = (await ai.get(f"/transactions/{txn}/category")).text
    assert form.count('class="chip"') == 2 and f"category_id.value='{r}'" in form
    # transakcja z kategorią — bez propozycji
    await ai.post(f"/transactions/{txn}/category", data={"category_id": str(s)})
    form = (await ai.get(f"/transactions/{txn}/category")).text
    assert 'class="chip"' not in form


async def test_country_group_shows_candidates_as_text(
    ai: httpx.AsyncClient, ai_service: Service
) -> None:
    add(ai_service.conn, "-80.00", "card", "ZXCVB 1 XYZ CHE 2026-09-10", day="2026-09-10")
    categorize.recategorize(ai_service.conn)
    _suggest(ai_service, "Zxcvb", "out", "noclegi", "restauracje")
    body = (
        await ai.get(
            "/review/group",
            params={
                "kind": "country",
                "value": "CHE",
                "direction": "out",
                "currency": "PLN",
                "gid": "c1",
            },
        )
    ).text
    assert "AI: Noclegi, Restauracje i kawiarnie" in body and 'class="chip' not in body


@respx.mock
async def test_review_run_now(ai: httpx.AsyncClient, ai_service: Service) -> None:
    content = {
        "items": [
            {
                "i": 0,
                "candidates": [
                    {"category_id": sid(ai_service.conn, "restauracje"), "confidence": 0.8},
                    {"category_id": sid(ai_service.conn, "spozywcze"), "confidence": 0.4},
                ],
            }
        ]
    }
    respx.post(f"{ROUTER}/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(content)}}], "usage": {}}
        )
    )
    r = await ai.post(
        "/review/ai-run", data={"direction": "out", "sort": "count", "month": "2026-09"}
    )
    assert r.status_code == 303 and r.headers["location"].endswith(
        "/review?direction=out&sort=count&month=2026-09"
    )
    page = (await ai.get("/review?month=2026-09")).text
    assert "zapisanych 1, bez podpowiedzi zostało 0" in page and page.count('class="chip ') == 2


# --- M4f/2: filtr kolejki po propozycji AI + „✓” -----------------------------------------------


def _three(service: Service) -> dict[str, int]:
    """Qwerty (z fixture'u) + Asdfg + Poiuy + grupa kraju; propozycje: restauracje u Qwerty
    (1.) i Asdfg (2.), u Poiuy tylko spożywcze."""
    conn = service.conn
    add(conn, "-12.00", "card", "ASDFG 3 XYZ POL 2026-09-02", day="2026-09-02")
    add(conn, "-14.00", "card", "ASDFG 3 XYZ POL 2026-09-04", day="2026-09-04")
    add(conn, "-40.00", "card", "POIUY 9 XYZ POL 2026-09-03", day="2026-09-03")
    add(conn, "-80.00", "card", "ZXCVB 1 XYZ CHE 2026-09-10", day="2026-09-10")
    categorize.recategorize(conn)
    _suggest(service, "Qwerty", "out", "restauracje", "spozywcze")
    _suggest(service, "Asdfg", "out", "spozywcze", "restauracje", "ogrod")
    _suggest(service, "Poiuy", "out", "spozywcze")
    return {"restauracje": sid(conn, "restauracje"), "spozywcze": sid(conn, "spozywcze")}


async def test_ai_filter_bar_and_list(ai: httpx.AsyncClient, ai_service: Service) -> None:
    ids = _three(ai_service)
    page = (await ai.get("/review")).text
    assert "Spożywcze (3)" in page and "Restauracje i kawiarnie (2)" in page
    assert page.index("Spożywcze (3)") < page.index("Restauracje i kawiarnie (2)")
    assert f"ai={ids['restauracje']}" in page and "Zagranica" in page
    assert "rv-accept" not in page  # bez filtra — tylko chipy
    page = (await ai.get(f"/review?ai={ids['restauracje']}&sort=count")).text
    assert "Qwerty" in page and "Asdfg" in page and "Poiuy" not in page
    assert "Zagranica" not in page  # grupy kraju nie mają propozycji
    assert page.count('class="rv-accept"') == 2
    assert 'aria-label="zatwierdź: Restauracje i kawiarnie"' in page
    assert f"pick={ids['restauracje']}" not in page  # chip = filtr — schowany, jest przycisk
    # filtr przenosi się do zakładek, sortowania i formularza „Podpowiedz teraz”
    assert f"direction=in&sort=count&amp;ai={ids['restauracje']}" in page
    assert f"sort=amount&amp;ai={ids['restauracje']}" in page
    assert f'name="ai" value="{ids["restauracje"]}"' in page
    # nieznana kategoria albo bez kandydatów — pusta lista, nie błąd
    page = (await ai.get("/review?ai=999999")).text
    assert "Nic do przejrzenia" in page and "pokaż wszystkie" in page


async def test_ai_filter_check_is_manual(ai: httpx.AsyncClient, ai_service: Service) -> None:
    ids = _three(ai_service)
    r = await ai.post(
        "/review/assign",
        data={
            "kind": "merchant",
            "value": "Asdfg",
            "direction": "out",
            "currency": "PLN",
            "gid": "m2",
            "category_id": str(ids["restauracje"]),
            "all": "1",
        },
    )
    assert "zapisano" in r.text and "Asdfg: 2 tr." in r.text and "reguła" not in r.text
    assert rules.all_rules(ai_service.conn) == []  # ✓ = kategoria ręczna, bez reguły
    sources = {
        row[0]
        for row in ai_service.conn.execute(
            "SELECT category_source FROM txn WHERE merchant = 'Asdfg'"
        )
    }
    assert sources == {"manual"}
    status = ai_service.conn.execute(
        "SELECT status FROM suggestion WHERE merchant = 'Asdfg'"
    ).fetchone()["status"]
    assert status == "accepted"
    page = (await ai.get(f"/review?ai={ids['restauracje']}")).text
    assert "Asdfg" not in page and "Restauracje i kawiarnie (1)" in page


async def test_ai_filter_ignored_when_ai_off(service: Service) -> None:
    service.conn.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', ?)",
        (db.now_iso(),),
    )
    add(service.conn, "-30.00", "card", "QWERTY 12 XYZ POL 2026-09-01", day="2026-09-01")
    categorize.recategorize(service.conn)
    [r] = _suggest(service, "Qwerty", "out", "restauracje")
    async with _client(service) as c:
        page = (await c.get(f"/review?ai={r}")).text
    assert "Qwerty" in page and "rv-accept" not in page and "Restauracje i kawiarnie (" not in page


async def test_ai_filter_bar_folds_long_tail(
    ai: httpx.AsyncClient, ai_service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    from budget.web import routes_review

    monkeypatch.setattr(routes_review, "AI_TOP", 1)
    ids = _three(ai_service)
    page = (await ai.get("/review")).text
    assert "więcej (2)" in page and '<details class="rv-f-more" >' in page
    assert page.index("Spożywcze (3)") < page.index("więcej (2)")
    assert page.index("więcej (2)") < page.index("Restauracje i kawiarnie (2)")
    # wybrana podkategoria z ogona — „więcej” rozwinięte
    page = (await ai.get(f"/review?ai={ids['restauracje']}")).text
    assert '<details class="rv-f-more" open>' in page
