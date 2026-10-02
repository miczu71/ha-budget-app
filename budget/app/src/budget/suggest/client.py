"""Klient API zgodnego z OpenAI (freellmapi) — jedno wywołanie z odpowiedzią wg schematu JSON.

Zachowanie routera zmierzone w innym add-onie użytkownika (nokia_tracker):
- `json_schema` działa tylko na nazwanym modelu (`auto` go nie obsługuje);
- `max_tokens` poniżej ~1500 ucina JSON u modeli z tokenami rozumowania;
- awarie dostawcy po drodze to HTTP 502, nie tylko 429 — oba ponawiane;
- typ „liczba albo null” psuł schemat na Gemini — schematy bez unii typów.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

MIN_MAX_TOKENS = 1500
RETRY_STATUSES = frozenset({429, 502, 503})
RETRY_DELAYS = (2.0, 6.0)
TIMEOUT = 90.0


class AIError(Exception):
    """Wywołanie nieudane — komunikat bez klucza, do logu i panelu."""


async def _post(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], body: dict[str, Any]
) -> httpx.Response:
    """POST z ponowieniami na 429/502/503 i błędy sieci."""
    for delay in (*RETRY_DELAYS, None):
        try:
            resp = await client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            if delay is None:
                raise AIError(f"brak połączenia z routerem AI ({type(exc).__name__})") from exc
        else:
            if resp.status_code == 200:
                return resp
            if resp.status_code not in RETRY_STATUSES or delay is None:
                raise AIError(f"router AI: HTTP {resp.status_code} — {resp.text[:200]}")
        await asyncio.sleep(delay)
    raise AIError("router AI: wyczerpane ponowienia")  # pragma: no cover


async def complete(
    *,
    base_url: str,
    api_key: str | None,
    model: str,
    prompt: str,
    schema: dict[str, Any],
    schema_name: str,
    max_tokens: int = 4000,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[dict[str, Any], int]:
    """(odpowiedź jako dict, zużyte tokeny)."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {
        "model": model,
        "max_tokens": max(max_tokens, MIN_MAX_TOKENS),
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
    }
    async with httpx.AsyncClient(timeout=TIMEOUT, transport=transport) as client:
        resp = await _post(client, f"{base_url}/chat/completions", headers, body)
    try:
        data = resp.json()
        result = json.loads(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AIError(f"router AI: nieczytelna odpowiedź ({exc})") from exc
    if not isinstance(result, dict):
        raise AIError("router AI: odpowiedź nie jest obiektem JSON")
    tokens = int((data.get("usage") or {}).get("total_tokens") or 0)
    return result, tokens
