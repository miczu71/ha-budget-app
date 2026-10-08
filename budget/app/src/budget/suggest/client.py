"""Klient API zgodnego z OpenAI (freellmapi) — jedno wywołanie z odpowiedzią wg schematu JSON.

Zachowanie routera zmierzone w innym add-onie użytkownika (nokia_tracker):
- `json_schema` działa na nazwanym modelu i na łańcuchu fallback `auto:<nazwa>` (np. `auto:text`,
  zmierzone 2026-10-08); samo `auto` nie ogłasza `response_format` w `/v1/models`;
- `max_tokens` poniżej ~1500 ucina JSON u modeli z tokenami rozumowania;
- awarie dostawcy po drodze to HTTP 502, nie tylko 429 — oba ponawiane;
- typ „liczba albo null” psuł schemat na Gemini — schematy bez unii typów.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

MIN_MAX_TOKENS = 1500
RETRY_STATUSES = frozenset({429, 502, 503})
RETRY_DELAYS = (2.0, 6.0)
TIMEOUT = 90.0
_RESET = re.compile(r"reset\D{0,12}(\d+\s*[hm])", re.IGNORECASE)

log = logging.getLogger(__name__)


class AIError(Exception):
    """Wywołanie nieudane — zdanie dla użytkownika panelu (bez klucza); surowa odpowiedź routera
    idzie do logu add-onu."""


def http_error(status: int, text: str, model: str) -> AIError:
    """Opisowy komunikat zamiast surowego „HTTP 429 — {json}” routera."""
    log.warning("router AI: HTTP %s (model %s): %s", status, model, text[:300])
    if status == 429:
        reset = _RESET.search(text)
        if reset is None:
            return AIError(
                f"Limit zapytań modelu AI „{model}” chwilowo wyczerpany — spróbuj za kilka minut "
                "albo wybierz inny model w opcji ai_model."
            )
        return AIError(
            f"Limit modelu AI „{model}” jest wyczerpany (darmowy dostawca nie przyjmuje więcej "
            f"zapytań). Odnowi się za ok. {reset.group(1).replace(' ', '')} — możesz też wybrać "
            "inny model w opcji ai_model."
        )
    if status in (401, 403):
        return AIError("Router AI odrzucił klucz — sprawdź opcję ai_api_key.")
    if status == 404:
        return AIError(f"Router AI nie zna modelu „{model}” — sprawdź opcję ai_model.")
    if status == 400:
        return AIError(
            f"Model „{model}” odrzucił zapytanie — może nie obsługiwać odpowiedzi według schematu "
            "JSON. Wybierz inny model w opcji ai_model."
        )
    if status >= 500:
        return AIError(
            f"Dostawca modelu AI „{model}” chwilowo nie odpowiada (HTTP {status}). "
            "Spróbuj za kilka minut."
        )
    return AIError(f"Router AI zwrócił błąd HTTP {status} dla modelu „{model}”.")


async def _post(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], body: dict[str, Any]
) -> httpx.Response:
    """POST z ponowieniami na 429/502/503 i błędy sieci."""
    for delay in (*RETRY_DELAYS, None):
        try:
            resp = await client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            if delay is None:
                raise AIError(
                    "Brak połączenia z routerem AI — sprawdź, czy działa i czy opcja ai_base_url "
                    f"jest poprawna ({type(exc).__name__})."
                ) from exc
        else:
            if resp.status_code == 200:
                return resp
            if resp.status_code not in RETRY_STATUSES or delay is None:
                raise http_error(resp.status_code, resp.text, str(body.get("model")))
        await asyncio.sleep(delay)
    raise AIError("Router AI nie odpowiedział po kilku próbach.")  # pragma: no cover


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
        log.warning("router AI: nieczytelna odpowiedź modelu %s: %s", model, exc)
        raise AIError(
            f"Model „{model}” zwrócił odpowiedź, której nie da się odczytać — spróbuj ponownie "
            "albo wybierz inny model w opcji ai_model."
        ) from exc
    if not isinstance(result, dict):
        raise AIError(
            f"Model „{model}” zwrócił odpowiedź w złym formacie — spróbuj ponownie albo wybierz "
            "inny model w opcji ai_model."
        )
    tokens = int((data.get("usage") or {}).get("total_tokens") or 0)
    return result, tokens
