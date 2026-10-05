"""Klient Supervisora, powiadomienia operacyjne i encje MQTT (bez brokera)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from budget import flex, ha_publisher, notifications, sessions
from budget.categorize import engine, taxonomy
from budget.eb_models import Balance, SessionResponse
from budget.ha_client import HAClient, HAError
from budget.ledger import account_by_alias, ingest_balances
from budget.snapshot import Snapshot
from budget.storage import db

from .test_categorize_engine import add, conn

__all__ = ["conn"]

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


def _entities(conn: db.sqlite3.Connection, **kw: Any) -> list[ha_publisher.Entity]:
    return ha_publisher.build_entities(Snapshot(conn), **kw)


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
    entities = {e.unique_id: e for e in _entities(_ledger(), now=NOW, today=NOW.date())}
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
    entities = {e.key: e for e in _entities(conn, now=NOW, today=date(2026, 10, 2))}
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
    pub._entities = _entities(_ledger(), now=NOW, today=NOW.date())
    await pub._publish_all(client)  # type: ignore[arg-type]
    configs = [t for t, _, _ in client.sent if t.endswith("/config")]
    assert len(configs) == len(pub._entities)
    assert all(retain for _, _, retain in client.sent)
    unknown = dict((t, p) for t, p, _ in client.sent)["budget/last_sync/state"]
    assert unknown == ha_publisher.STATE_UNKNOWN
    client.sent.clear()
    await pub._publish_all(client)  # type: ignore[arg-type]
    assert not [t for t, _, _ in client.sent if t.endswith("/config")]


# --- encje budżetu Flex (M5a) ---------------------------------------------------------------


def _flex(conn: db.sqlite3.Connection, today: date) -> dict[str, ha_publisher.Entity]:
    engine.recategorize(conn)
    entities = _entities(conn, now=NOW, today=today)
    return {e.key: e for e in entities if e.key.startswith("flex_")}


def test_flex_entities_without_budget(conn: db.sqlite3.Connection) -> None:
    add(conn, "-100.00", "card", "LIDL XYZ POL", day="2026-09-02")
    add(conn, "-40.00", "card", "SKLEP ABC XYZ", day="2026-09-04")  # bez kategorii
    add(conn, "-55.00", "card", "LIDL XYZ POL", day="2026-08-20")  # poprzedni miesiąc
    f = _flex(conn, date(2026, 9, 10))
    assert set(f) == {"flex_budget", "flex_spent", "flex_remaining", "flex_per_day"}
    assert f["flex_spent"].state == "140.00"
    assert f["flex_spent"].attributes == {
        "uncategorized_amount": "40.00",
        "uncategorized_count": 1,
        "other_currency": 0,
        "month": "2026-09",
    }
    assert f["flex_budget"].state is None and f["flex_budget"].attributes["suggested"] == "60.00"
    assert f["flex_remaining"].state is None and f["flex_per_day"].state is None
    assert f["flex_remaining"].attributes["over_pace"] is False
    assert f["flex_remaining"].attributes["used_pct"] is None
    _, payload = f["flex_remaining"].discovery()
    assert payload["default_entity_id"] == "sensor.budget_flex_remaining"
    assert payload["device_class"] == "monetary" and payload["unit_of_measurement"] == "PLN"
    assert "state_class" not in payload  # bez statystyk długoterminowych (decyzja 10)


def test_flex_entities_with_budget(conn: db.sqlite3.Connection) -> None:
    add(conn, "-120.00", "card", "LIDL XYZ POL", day="2026-09-02")
    flex.set_budget(conn, date(2026, 8, 1), Decimal("3000"))
    f = _flex(conn, date(2026, 9, 10))  # wrzesień: 30 dni, dziś 10. → zostaje 21 dni
    assert f["flex_budget"].state == "3000.00"
    assert f["flex_budget"].attributes["budget_from"] == "2026-08"
    assert f["flex_remaining"].state == "2880.00"
    assert f["flex_remaining"].attributes == {
        "per_day": "137.14",
        "expected_today": "1000.00",
        "over_pace": False,
        "used_pct": 4.0,
        "days_left": 21,
        "month": "2026-09",
    }
    assert f["flex_per_day"].state == "137.14"
    last = _flex(conn, date(2026, 9, 30))
    assert last["flex_per_day"].state == last["flex_remaining"].state == "2880.00"
    october = _flex(conn, date(2026, 10, 1))  # zawsze bieżący miesiąc
    assert october["flex_spent"].state == "0.00"
    assert october["flex_remaining"].attributes["month"] == "2026-10"


def test_flex_over_pace_and_exhausted(conn: db.sqlite3.Connection) -> None:
    add(conn, "-400.00", "card", "LIDL XYZ POL", day="2026-09-02")
    flex.set_budget(conn, date(2026, 9, 1), Decimal("300"))
    f = _flex(conn, date(2026, 9, 10))
    assert f["flex_remaining"].state == "-100.00"
    assert f["flex_remaining"].attributes["over_pace"] is True
    assert f["flex_per_day"].state == "0.00"


def test_flex_error_does_not_block_other_entities(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: object) -> None:
        raise RuntimeError("x")

    monkeypatch.setattr(ha_publisher.flex, "build", boom)
    keys = {e.key for e in _entities(_ledger(), now=NOW, today=NOW.date())}
    assert "saldo_current_pln" in keys and "sync_now" in keys
    assert not any(k.startswith("flex_") for k in keys)


def test_flex_entities_auto_pool(conn: db.sqlite3.Connection) -> None:
    for m in ("2026-06", "2026-07", "2026-08"):
        t = add(conn, "9000.00", "transfer_in", f"Pensja {m}", "FIRMA X", day=f"{m}-24")
        engine.set_manual(conn, t, taxonomy.by_slug(conn)["wynagrodzenie"].id)
    f = _flex(conn, date(2026, 9, 10))
    assert f["flex_budget"].state == "9000.00"
    attrs = f["flex_budget"].attributes
    assert (attrs["source"], attrs["auto_amount"], attrs["income_base"]) == (
        "auto",
        "9000.00",
        "9000.00",
    )
    assert (attrs["bonus_excluded"], attrs["fixed_median"], attrs["income_drop_pct"]) == (
        "0.00",
        "0.00",
        None,
    )
    assert attrs["fixed_series"] == "0.00"
    assert f["flex_remaining"].state == "9000.00"


# --- encje płatności cyklicznych (M5b E2) ---------------------------------------------------


def test_recurring_entities(conn: db.sqlite3.Connection) -> None:
    from budget.categorize.rules import Conditions, TextCondition
    from budget.recurring import series as S

    add(conn, "-43.00", "transfer_out", "Abonament", "Qwertyflix Sp", day="2026-10-01")
    for name, direction, amount, anchor in (
        ("Qwertyflix", "out", "43", 1),
        ("Czynsz wymyślony", "out", "1000", 28),
        ("Pensja wymyślona", "in", "5000", 24),
    ):
        merchant = "Qwertyflix Sp" if name == "Qwertyflix" else "Nikt Taki"
        S.insert(
            conn,
            name=name,
            direction=direction,
            cadence="M",
            conditions=Conditions(
                text=(TextCondition("merchant", "equals", merchant),), direction=direction
            ),
            expected=Decimal(amount),
            tolerance=Decimal("5"),
            anchor_day=anchor,
            status="active",
            origin="manual",
            key=None,
        )
    ents = _entities(conn, now=NOW, today=NOW.date())
    e = {x.key: x for x in ents if x.key in ("fixed_paid", "fixed_planned", "income_planned")}
    assert set(e) == {"fixed_paid", "fixed_planned", "income_planned"}
    assert e["fixed_paid"].state == "43.00" and e["fixed_paid"].attributes["paid_count"] == 1
    assert e["fixed_planned"].state == "1000.00"
    assert e["income_planned"].state == "5000.00"
    assert e["income_planned"].attributes["items"][0]["status"] == "expected"
    _, payload = e["fixed_paid"].discovery()
    assert payload["default_entity_id"] == "sensor.budget_fixed_paid"
