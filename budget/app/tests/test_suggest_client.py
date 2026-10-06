"""Klient routera AI (OpenAI-compatible): schemat w żądaniu, ponowienia, błędy."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from budget.suggest import client
from budget.suggest.client import AIError

URL = "http://router:3003/v1"
SCHEMA = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}


def _ok(content: object, tokens: int = 50) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps(content)}}],
            "usage": {"total_tokens": tokens},
        },
    )


async def _call(**kw: object) -> tuple[dict[str, object], int]:
    return await client.complete(
        base_url=URL,
        api_key="sekret",
        model="model-x",
        prompt="p",
        schema=SCHEMA,
        schema_name="kategorie",
        **kw,  # type: ignore[arg-type]
    )


@pytest.fixture(autouse=True)
def no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "RETRY_DELAYS", (0.0, 0.0))


@respx.mock
async def test_request_shape_and_result() -> None:
    route = respx.post(f"{URL}/chat/completions").mock(return_value=_ok({"items": []}, 77))
    assert await _call(max_tokens=300) == ({"items": []}, 77)
    req = route.calls.last.request
    assert req.headers["authorization"] == "Bearer sekret"
    body = json.loads(req.content)
    assert body["model"] == "model-x" and body["temperature"] == 0
    assert body["max_tokens"] == client.MIN_MAX_TOKENS  # podniesione z 300
    rf = body["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"] == SCHEMA


@respx.mock
async def test_retries_on_502_then_succeeds() -> None:
    route = respx.post(f"{URL}/chat/completions").mock(
        side_effect=[httpx.Response(502, text="provider_error"), _ok({"items": []})]
    )
    assert (await _call())[0] == {"items": []}
    assert route.call_count == 2


@respx.mock
async def test_errors() -> None:
    respx.post(f"{URL}/chat/completions").mock(return_value=httpx.Response(401, text="nope"))
    with pytest.raises(AIError, match="odrzucił klucz"):
        await _call()
    respx.post(f"{URL}/chat/completions").mock(return_value=httpx.Response(503))
    with pytest.raises(AIError, match=r"„model-x” chwilowo nie odpowiada \(HTTP 503\)"):
        await _call()
    respx.post(f"{URL}/chat/completions").mock(return_value=httpx.Response(404))
    with pytest.raises(AIError, match="nie zna modelu „model-x”"):
        await _call()
    respx.post(f"{URL}/chat/completions").mock(return_value=httpx.Response(400))
    with pytest.raises(AIError, match="schematu JSON"):
        await _call()
    respx.post(f"{URL}/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "nie json"}}]})
    )
    with pytest.raises(AIError, match="nie da się odczytać"):
        await _call()
    respx.post(f"{URL}/chat/completions").mock(return_value=_ok([1, 2]))
    with pytest.raises(AIError, match="złym formacie"):
        await _call()
    respx.post(f"{URL}/chat/completions").mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(AIError, match="Brak połączenia z routerem AI"):
        await _call()


@respx.mock
async def test_rate_limit_message_has_reset_time_not_raw_json() -> None:
    raw = (
        '{"error":{"message":"All models exhausted: 1 route checked (1 rate-limited or on '
        'cooldown). Add more API keys or wait for rate limits to reset. Soonest reset ~11h.",'
        '"type":"rate_limit_error"}}'
    )
    route = respx.post(f"{URL}/chat/completions").mock(return_value=httpx.Response(429, text=raw))
    with pytest.raises(AIError) as err:
        await _call()
    msg = str(err.value)
    assert "Limit modelu AI „model-x” jest wyczerpany" in msg and "za ok. 11h" in msg
    assert "{" not in msg and "rate_limit_error" not in msg
    assert route.call_count == 3  # 429 nadal ponawiane (krótkie limity minutowe)
    route.mock(return_value=httpx.Response(429, text="Too Many Requests"))
    with pytest.raises(AIError, match="chwilowo wyczerpany"):
        await _call()
