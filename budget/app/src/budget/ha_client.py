"""Supervisor / Home Assistant Core API z wnętrza add-onu (`SUPERVISOR_TOKEN`)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import httpx
from websockets.asyncio.client import connect

log = logging.getLogger(__name__)

SUPERVISOR_URL = "http://supervisor"


class HAError(Exception):
    pass


class HAClient:
    def __init__(
        self,
        token: str | None,
        *,
        base_url: str = SUPERVISOR_URL,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._base = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        self._owns_http = http is None

    @property
    def available(self) -> bool:
        return bool(self._token)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self._token:
            raise HAError("brak SUPERVISOR_TOKEN (uruchomienie poza Supervisorem)")
        try:
            response = await self._http.request(
                method,
                f"{self._base}{path}",
                headers={"Authorization": f"Bearer {self._token}"},
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise HAError(f"{method} {path}: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise HAError(f"{method} {path}: HTTP {response.status_code}")
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    # --- Supervisor -------------------------------------------------------------------------

    async def mqtt_service(self) -> dict[str, Any] | None:
        """Dane brokera z usługi `mqtt` (Mosquitto) — None, gdy usługa nie istnieje."""
        try:
            data = await self._request("GET", "/services/mqtt")
        except HAError as exc:
            log.warning("Usługa MQTT niedostępna: %s", exc)
            return None
        payload = data.get("data") if isinstance(data, dict) else None
        return payload if isinstance(payload, dict) and payload.get("host") else None

    async def self_slug(self) -> str | None:
        """Slug add-onu (z prefiksem repozytorium) — do linku do panelu."""
        try:
            data = await self._request("GET", "/addons/self/info")
        except HAError:
            return None
        info = data.get("data") if isinstance(data, dict) else None
        slug = info.get("slug") if isinstance(info, dict) else None
        return slug if isinstance(slug, str) else None

    # --- Core -------------------------------------------------------------------------------

    async def call_service(self, domain: str, service: str, data: dict[str, Any]) -> None:
        await self._request("POST", f"/core/api/services/{domain}/{service}", json=data)

    async def get_state(self, entity_id: str) -> dict[str, Any] | None:
        """Stan encji z Core; None, gdy encja nie istnieje (404)."""
        try:
            data = await self._request("GET", f"/core/api/states/{entity_id}")
        except HAError as exc:
            if str(exc).endswith("HTTP 404"):
                return None
            raise
        return data if isinstance(data, dict) else None

    async def monthly_statistics(
        self, entity_ids: list[str], start: datetime, end: datetime
    ) -> dict[str, list[dict[str, Any]]]:
        """Statystyki miesięczne (recorder/statistics_during_period) przez WebSocket Core."""
        if not self._token:
            raise HAError("brak SUPERVISOR_TOKEN (uruchomienie poza Supervisorem)")
        url = f"ws{self._base[4:]}/core/websocket"
        try:
            async with asyncio.timeout(15):
                async with connect(url) as ws:
                    first = json.loads(await ws.recv())
                    if first.get("type") != "auth_required":
                        raise HAError("WS: oczekiwano auth_required")
                    await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
                    if json.loads(await ws.recv()).get("type") != "auth_ok":
                        raise HAError("WS: autoryzacja odrzucona")
                    await ws.send(
                        json.dumps(
                            {
                                "id": 1,
                                "type": "recorder/statistics_during_period",
                                "start_time": start.isoformat(),
                                "end_time": end.isoformat(),
                                "statistic_ids": entity_ids,
                                "period": "month",
                                "types": ["state", "mean"],
                            }
                        )
                    )
                    reply = json.loads(await ws.recv())
        except HAError:
            raise
        except Exception as exc:
            raise HAError(f"WS statistics: {type(exc).__name__}") from exc
        if not isinstance(reply, dict) or not reply.get("success"):
            raise HAError("WS statistics: success=false")
        result = reply.get("result")
        if not isinstance(result, dict):
            raise HAError("WS statistics: brak wyniku")
        return {str(k): v for k, v in result.items() if isinstance(v, list)}

    async def persistent_notification(self, notification_id: str, title: str, message: str) -> None:
        await self.call_service(
            "persistent_notification",
            "create",
            {"notification_id": notification_id, "title": title, "message": message},
        )

    async def dismiss_notification(self, notification_id: str) -> None:
        await self.call_service(
            "persistent_notification", "dismiss", {"notification_id": notification_id}
        )

    async def notify(
        self, service: str, title: str, message: str, data: dict[str, Any] | None = None
    ) -> None:
        """`service` w postaci `notify.<nazwa>` (alias osoby)."""
        domain, _, name = service.partition(".")
        if domain != "notify" or not name:
            raise HAError(f"oczekiwana usługa notify.<nazwa>, a jest {service!r}")
        payload: dict[str, Any] = {"title": title, "message": message}
        if data:
            payload["data"] = data
        await self.call_service("notify", name, payload)

    async def update_entity(self, entity_id: str) -> None:
        await self.call_service("homeassistant", "update_entity", {"entity_id": entity_id})
