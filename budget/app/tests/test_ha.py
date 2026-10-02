"""Klient Supervisora, powiadomienia operacyjne i encje MQTT (bez brokera)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from budget import ha_publisher, notifications, sessions
from budget.eb_models import Balance, SessionResponse
from budget.ha_client import HAClient, HAError
from budget.ledger import account_by_alias, ingest_balances
from budget.storage import db

SUP = "http://supervisor"
FIXTURES = Path(__file__).parent / "fixtures"
SESSION = json.loads((FIXTURES / "eb_mock_session.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 10, 2, 8, 0, tzinfo=UTC)


@pytest.fixture
async def ha() -> AsyncIterator[HAClient]:
    async with httpx.AsyncClient() as http:
        yield HAClient("tok", http=http)


# --- HAClient -------------------------------------------------------------------------------


@respx.mock
async def test_mqtt_service_and_slug(ha: HAClient) -> None:
    route = respx.get(f"{SUP}/services/mqtt").mock(
        return_value=httpx.Response(
            200, json={"result": "ok", "data": {"host": "core-mosquitto", "port": 1883}}
        )
    )
    assert (await ha.mqtt_service()) == {"host": "core-mosquitto", "port": 1883}
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"
    respx.get(f"{SUP}/addons/self/info").mock(
        return_value=httpx.Response(200, json={"data": {"slug": "abc123_budget"}})
    )
    assert await ha.self_slug() == "abc123_budget"


@respx.mock
async def test_mqtt_service_missing(ha: HAClient) -> None:
    respx.get(f"{SUP}/services/mqtt").mock(return_value=httpx.Response(400))
    assert await ha.mqtt_service() is None


@respx.mock
async def test_notify_and_persistent(ha: HAClient) -> None:
    pn = respx.post(f"{SUP}/core/api/services/persistent_notification/create").mock(
        return_value=httpx.Response(200, json=[])
    )
    nt = respx.post(f"{SUP}/core/api/services/notify/osoba").mock(
        return_value=httpx.Response(200, json=[])
    )
    await ha.persistent_notification("budget_x", "T", "M")
    await ha.notify("notify.osoba", "T", "M")
    assert json.loads(pn.calls.last.request.content)["notification_id"] == "budget_x"
    assert json.loads(nt.calls.last.request.content) == {"title": "T", "message": "M"}
    with pytest.raises(HAError):
        await ha.notify("light.x", "T", "M")


async def test_without_token() -> None:
    ha = HAClient(None)
    assert not ha.available
    with pytest.raises(HAError, match="SUPERVISOR_TOKEN"):
        await ha.persistent_notification("a", "b", "c")
    await ha.aclose()


# --- notifications --------------------------------------------------------------------------


def _record(status: str = "AUTHORIZED", days: int = 100) -> sessions.SessionRecord:
    return sessions.SessionRecord("s", "Bank", NOW + timedelta(days=days), status, None, [])


def test_evaluate() -> None:
    kw: dict[str, Any] = {"failures": 0, "manual_sync_needed": False, "warning_days": 14}
    assert notifications.evaluate(_record(), now=NOW, **kw) == []
    assert notifications.evaluate(None, now=NOW, **kw) == []
    keys = [a.key for a in notifications.evaluate(_record(days=10), now=NOW, **kw)]
    assert keys == ["consent_expiring"]
    keys = [a.key for a in notifications.evaluate(_record("EXPIRED", 0), now=NOW, **kw)]
    assert keys == ["session_inactive"]
    kw.update(failures=3, manual_sync_needed=True)
    keys = [a.key for a in notifications.evaluate(_record(), now=NOW, **kw)]
    assert keys == ["sync_failures", "manual_sync"]


@respx.mock
async def test_notifier_dedup_and_dismiss(ha: HAClient) -> None:
    conn = db.connect(":memory:")
    pn = respx.post(f"{SUP}/core/api/services/persistent_notification/create").mock(
        return_value=httpx.Response(200)
    )
    nt = respx.post(f"{SUP}/core/api/services/notify/osoba").mock(return_value=httpx.Response(200))
    dismiss = respx.post(f"{SUP}/core/api/services/persistent_notification/dismiss").mock(
        return_value=httpx.Response(200)
    )
    notifier = notifications.Notifier(ha, notify_service="notify.osoba", panel_url="/x")
    alert = notifications.Alert("sync_failures", "3 nieudane")
    await notifier.process(conn, [alert], NOW)
    await notifier.process(conn, [alert], NOW + timedelta(hours=1))  # bez powtórki
    assert pn.call_count == 1 and nt.call_count == 1
    assert "[Otwórz panel Budżetu](/x)" in json.loads(pn.calls.last.request.content)["message"]
    await notifier.process(conn, [alert], NOW + timedelta(hours=25))  # przypomnienie
    assert pn.call_count == 2
    await notifier.process(conn, [], NOW + timedelta(hours=26))  # ustało → dismiss
    assert dismiss.call_count == 1
    assert db.kv_get(conn, notifications.STATE_KEY) is None


# --- encje MQTT -----------------------------------------------------------------------------


def _ledger() -> db.sqlite3.Connection:
    conn = db.connect(":memory:")
    sessions.store_session(conn, SessionResponse.from_api(SESSION))
    account = account_by_alias(conn, "eb_uid", SESSION["accounts"][0]["uid"])
    assert account is not None
    balances = [
        Balance.from_api({"balance_amount": {"currency": "PLN", "amount": a}, "balance_type": t})
        for t, a in (("ITAV", "1234.50"), ("ITBD", "1200.00"))
    ]
    ingest_balances(conn, account, balances, fetched_at="2026-10-02T06:00:00+00:00")
    return conn


def test_build_entities() -> None:
    entities = {
        e.unique_id: e for e in ha_publisher.build_entities(_ledger(), now=NOW, today=NOW.date())
    }
    saldo = entities["budget_saldo_current_pln"]
    assert saldo.state == "1234.50"
    assert saldo.attributes["balance_itbd"] == "1200.00"
    assert saldo.attributes["account"] is None or "*" in saldo.attributes["account"]
    topic, payload = saldo.discovery()
    assert topic == "homeassistant/sensor/budget_saldo_current_pln/config"
    assert payload["default_entity_id"] == "sensor.budget_saldo_current_pln"
    assert payload["device_class"] == "monetary" and payload["unit_of_measurement"] == "PLN"
    assert payload["availability_topic"] == "budget/availability"
    assert entities["budget_consent_days_left"].state == str((SESSION_UNTIL - NOW).days)
    assert entities["budget_sync_problem"].state == "OFF"
    assert entities["budget_last_sync"].state is None
    assert entities["budget_requests_today"].state == "0"
    _, button = entities["budget_sync_now"].discovery()
    assert button["command_topic"] == ha_publisher.SYNC_NOW_TOPIC and "state_topic" not in button


SESSION_UNTIL = datetime(2027, 3, 30, 10, 57, 35, tzinfo=UTC)


def test_entities_without_session() -> None:
    conn = db.connect(":memory:")
    entities = {
        e.key: e for e in ha_publisher.build_entities(conn, now=NOW, today=date(2026, 10, 2))
    }
    assert entities["consent_days_left"].state is None
    assert entities["sync_problem"].state == "ON"
    assert not any(k.startswith("saldo_") for k in entities)


class FakeClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, bool]] = []

    async def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        self.sent.append((topic, payload, retain))


async def test_publish_all_republishes_only_changed_config() -> None:
    async def noop() -> None:
        return None

    pub = ha_publisher.Publisher(
        host="h", port=1883, username=None, password=None, on_sync_now=noop
    )
    client = FakeClient()
    pub._entities = ha_publisher.build_entities(_ledger(), now=NOW, today=NOW.date())
    await pub._publish_all(client)  # type: ignore[arg-type]
    configs = [t for t, _, _ in client.sent if t.endswith("/config")]
    assert len(configs) == len(pub._entities)
    assert all(retain for _, _, retain in client.sent)
    unknown = dict((t, p) for t, p, _ in client.sent)["budget/last_sync/state"]
    assert unknown == ha_publisher.STATE_UNKNOWN
    client.sent.clear()
    await pub._publish_all(client)  # type: ignore[arg-type]
    assert not [t for t, _, _ in client.sent if t.endswith("/config")]
