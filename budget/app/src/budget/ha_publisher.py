"""Encje HA przez MQTT Discovery (SPEC §6.1, zakres M3).

Jedno urządzenie „Budżet Domowy”; dostępność przez LWT (`budget/availability`), konfiguracje
i stany retained. `default_entity_id` przypina entity_id (od HA 2026.4 `object_id` jest
ignorowane). Przycisk `sync_now` przychodzi tematem komend.

`build_entities()` jest czystą funkcją stanu księgi → encje (testowana bez brokera).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sqlite3
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import aiomqtt

from budget import __version__, sessions, sync_service
from budget.logging_utils import mask_iban

log = logging.getLogger(__name__)

NODE = "budget"
DISCOVERY_PREFIX = "homeassistant"
AVAILABILITY_TOPIC = f"{NODE}/availability"
SYNC_NOW_TOPIC = f"{NODE}/cmd/sync_now"
DEVICE = {
    "identifiers": [NODE],
    "name": "Budżet Domowy",
    "manufacturer": "ha-budget-app",
    "model": "Add-on Home Assistant",
    "sw_version": __version__,
}
RECONNECT_DELAY = (5, 15, 60)
STATE_UNKNOWN = "None"  # HA MQTT: payload „None” = stan unknown


@dataclass(frozen=True)
class Entity:
    component: str
    key: str  # unikalny w urządzeniu: entity_id = <component>.budget_<key>
    config: dict[str, Any]
    state: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def unique_id(self) -> str:
        return f"{NODE}_{self.key}"

    @property
    def state_topic(self) -> str:
        return f"{NODE}/{self.key}/state"

    @property
    def attributes_topic(self) -> str:
        return f"{NODE}/{self.key}/attributes"

    def discovery(self) -> tuple[str, dict[str, Any]]:
        payload: dict[str, Any] = {
            "unique_id": self.unique_id,
            "default_entity_id": f"{self.component}.{self.unique_id}",
            "device": DEVICE,
            "availability_topic": AVAILABILITY_TOPIC,
            **self.config,
        }
        if self.component != "button":
            payload["state_topic"] = self.state_topic
            payload["json_attributes_topic"] = self.attributes_topic
        return f"{DISCOVERY_PREFIX}/{self.component}/{self.unique_id}/config", payload


def _balance_key(kind: str, currency: str, taken: set[str], account_id: int) -> str:
    key = f"saldo_{kind}_{currency.lower()}"
    return f"{key}_{account_id}" if key in taken else key


def build_entities(conn: sqlite3.Connection, *, now: datetime, today: date) -> list[Entity]:
    entities: list[Entity] = []
    taken: set[str] = set()
    for acc in conn.execute("SELECT * FROM account ORDER BY id").fetchall():
        snaps = {
            r["balance_type"]: r
            for r in conn.execute(
                "SELECT * FROM balance_snapshot WHERE account_id = ? AND fetched_at = "
                "(SELECT max(fetched_at) FROM balance_snapshot WHERE account_id = ?)",
                (acc["id"], acc["id"]),
            )
        }
        if not snaps:
            continue
        main = snaps.get("ITAV") or snaps.get("ITBD") or next(iter(snaps.values()))
        key = _balance_key(acc["kind"], acc["currency"], taken, int(acc["id"]))
        taken.add(key)
        label = acc["display_name"] or acc["product"] or f"Konto {acc['id']}"
        entities.append(
            Entity(
                "sensor",
                key,
                {
                    "name": f"Dostępne — {label}",
                    "device_class": "monetary",
                    "state_class": "total",
                    "unit_of_measurement": acc["currency"],
                    "suggested_display_precision": 2,
                    "icon": "mdi:credit-card" if acc["kind"] == "card" else "mdi:bank",
                },
                state=main["amount"],
                attributes={
                    "account": mask_iban(acc["iban"]),
                    "kind": acc["kind"],
                    "balance_type": main["balance_type"],
                    **{f"balance_{t.lower()}": r["amount"] for t, r in snaps.items()},
                    "reference_date": main["reference_date"],
                    "fetched_at": main["fetched_at"],
                },
            )
        )
    record = sessions.current(conn)
    entities.append(
        Entity(
            "sensor",
            "consent_days_left",
            {"name": "Zgoda bankowa — dni", "unit_of_measurement": "d", "icon": "mdi:bank-check"},
            state=str(record.days_left(now)) if record and record.active else None,
            attributes={
                "valid_until": record.valid_until.isoformat() if record else None,
                "status": record.status if record else "brak połączenia",
                "bank": record.aspsp if record else None,
            },
        )
    )
    last = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
    last_ok = conn.execute(
        "SELECT finished_at FROM sync_log WHERE status IN ('ok', 'partial') "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    entities.append(
        Entity(
            "sensor",
            "last_sync",
            {"name": "Ostatnia synchronizacja", "device_class": "timestamp"},
            state=last_ok["finished_at"] if last_ok else None,
            attributes={
                "last_status": last["status"] if last else None,
                "last_attempt": last["finished_at"] if last else None,
                "new_transactions": last["new_txn"] if last else None,
                "detail": last["detail"] if last else None,
            },
        )
    )
    failures = sync_service.consecutive_failures(conn)
    problem = (record is None or not record.active) or failures > 0
    entities.append(
        Entity(
            "binary_sensor",
            "sync_problem",
            {"name": "Problem z synchronizacją", "device_class": "problem"},
            state="ON" if problem else "OFF",
            attributes={"consecutive_failures": failures},
        )
    )
    entities.append(
        Entity(
            "sensor",
            "requests_today",
            {
                "name": "Zapytania do banku dziś (max na konto)",
                "entity_category": "diagnostic",
                "icon": "mdi:counter",
                "state_class": "measurement",
            },
            state=str(sync_service.max_requests_today(conn, today)),
            attributes={"limit": sync_service.DAILY_LIMIT, "day": today.isoformat()},
        )
    )
    entities.append(
        Entity(
            "button",
            "sync_now",
            {
                "name": "Synchronizuj teraz",
                "command_topic": SYNC_NOW_TOPIC,
                "payload_press": "PRESS",
                "icon": "mdi:sync",
            },
        )
    )
    return entities


class Publisher:
    """Połączenie z brokerem w tle, z ponawianiem; publikuje ostatni znany stan encji."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        on_sync_now: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        self._params = {"hostname": host, "port": port, "username": username, "password": password}
        self._on_sync_now = on_sync_now
        self._client: aiomqtt.Client | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._entities: list[Entity] = []
        self._published: dict[str, str] = {}  # temat discovery → ostatni payload

    @property
    def connected(self) -> bool:
        return self._client is not None

    async def run(self) -> None:
        attempt = 0
        while True:
            try:
                async with aiomqtt.Client(
                    **self._params,  # type: ignore[arg-type]
                    identifier="ha-budget-app",
                    will=aiomqtt.Will(AVAILABILITY_TOPIC, "offline", retain=True),
                ) as client:
                    self._client = client
                    self._published.clear()  # po ponownym połączeniu wszystko od nowa
                    attempt = 0
                    log.info("MQTT połączone")
                    await client.publish(AVAILABILITY_TOPIC, "online", retain=True)
                    await self._publish_all(client)
                    await client.subscribe(SYNC_NOW_TOPIC)
                    async for message in client.messages:
                        if str(message.topic) == SYNC_NOW_TOPIC:
                            task = asyncio.create_task(self._on_sync_now())
                            self._tasks.add(task)
                            task.add_done_callback(self._tasks.discard)
            except aiomqtt.MqttError as exc:
                self._client = None
                delay = RECONNECT_DELAY[min(attempt, len(RECONNECT_DELAY) - 1)]
                attempt += 1
                log.warning("MQTT rozłączone (%s) — ponowna próba za %d s", exc, delay)
                await asyncio.sleep(delay)
            finally:
                self._client = None

    async def update(self, entities: list[Entity]) -> None:
        self._entities = entities
        if self._client is not None:
            try:
                await self._publish_all(self._client)
            except aiomqtt.MqttError as exc:
                log.warning("MQTT: publikacja nieudana (%s)", exc)

    async def _publish_all(self, client: aiomqtt.Client) -> None:
        for entity in self._entities:
            topic, payload = entity.discovery()
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            if self._published.get(topic) != body:  # zmiana konfiguracji (np. nazwa konta)
                await client.publish(topic, body, retain=True)
                self._published[topic] = body
            if entity.component == "button":
                continue
            await client.publish(
                entity.state_topic,
                entity.state if entity.state is not None else STATE_UNKNOWN,
                retain=True,
            )
            await client.publish(
                entity.attributes_topic,
                json.dumps(entity.attributes, ensure_ascii=False, default=str),
                retain=True,
            )

    async def offline(self) -> None:
        if self._client is not None:
            with contextlib.suppress(aiomqtt.MqttError):
                await self._client.publish(AVAILABILITY_TOPIC, "offline", retain=True)
