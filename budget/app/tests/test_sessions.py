"""Sesje EB w bazie add-onu: import z CLI (bez SCA) i autoryzacja z panelu."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest
import respx

from budget import sessions
from budget.eb_client import EBAuthError, EBClient
from budget.storage import db

from .conftest import BASE

FIXTURES = Path(__file__).parent / "fixtures"
SESSION_BYTES = (FIXTURES / "eb_mock_session.json").read_bytes()
SESSION = json.loads(SESSION_BYTES)


def _info(status: str = "AUTHORIZED") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": status,
            "access": {"valid_until": "2027-03-30T10:57:35Z"},
            "accounts": [a["uid"] for a in SESSION["accounts"]],
        },
    )


@pytest.fixture
def conn() -> db.sqlite3.Connection:
    return db.connect(":memory:")


@respx.mock
async def test_import_session_file(conn: db.sqlite3.Connection, eb: EBClient) -> None:
    route = respx.get(f"{BASE}/sessions/{SESSION['session_id']}").mock(return_value=_info())
    record = await sessions.import_session_file(conn, eb, SESSION_BYTES)
    assert route.call_count == 1
    assert record.session_id == SESSION["session_id"]
    assert record.active and record.aspsp == "Mock ASPSP"
    assert record.valid_until == datetime(2027, 3, 30, 10, 57, 35, tzinfo=UTC)
    assert record.days_left(datetime(2027, 3, 1, tzinfo=UTC)) == 29
    assert len(record.accounts) == 3
    # konta i aliasy uid w księdze
    uids = {r[0] for r in conn.execute("SELECT value FROM account_alias WHERE source = 'eb_uid'")}
    assert uids == {a["uid"] for a in SESSION["accounts"]}
    assert sessions.current(conn) == record


@respx.mock
async def test_import_is_idempotent_and_replaces_current(
    conn: db.sqlite3.Connection, eb: EBClient
) -> None:
    respx.get(url__regex=rf"{BASE}/sessions/.*").mock(return_value=_info())
    await sessions.import_session_file(conn, eb, SESSION_BYTES)
    await sessions.import_session_file(conn, eb, SESSION_BYTES)
    assert conn.execute("SELECT count(*) FROM eb_session").fetchone()[0] == 1
    other = {**SESSION, "session_id": "s-nowa"}
    await sessions.import_session_file(conn, eb, json.dumps(other).encode())
    rows = conn.execute("SELECT session_id, is_current FROM eb_session ORDER BY 1").fetchall()
    assert [(r[0], r[1]) for r in rows] == sorted([(SESSION["session_id"], 0), ("s-nowa", 1)])
    # te same konta — bez duplikatów
    assert conn.execute("SELECT count(*) FROM account").fetchone()[0] == len(
        {a["account_id"]["iban"] for a in SESSION["accounts"]}
    )


@respx.mock
async def test_import_rejects_inactive_session(conn: db.sqlite3.Connection, eb: EBClient) -> None:
    respx.get(f"{BASE}/sessions/{SESSION['session_id']}").mock(return_value=_info("EXPIRED"))
    with pytest.raises(sessions.SessionError, match="EXPIRED"):
        await sessions.import_session_file(conn, eb, SESSION_BYTES)
    assert sessions.current(conn) is None


@pytest.mark.parametrize("data", [b"not json", b'{"foo": 1}', b"[1, 2]"])
def test_parse_session_file_errors(data: bytes) -> None:
    with pytest.raises(sessions.SessionError):
        sessions.parse_session_file(data)


@respx.mock
async def test_refresh_status(conn: db.sqlite3.Connection, eb: EBClient) -> None:
    route = respx.get(f"{BASE}/sessions/{SESSION['session_id']}").mock(return_value=_info())
    assert await sessions.refresh_status(conn, eb) is None
    await sessions.import_session_file(conn, eb, SESSION_BYTES)
    route.mock(return_value=_info("REVOKED"))
    record = await sessions.refresh_status(conn, eb)
    assert record is not None and record.status == "REVOKED" and not record.active


@respx.mock
async def test_auth_flow(conn: db.sqlite3.Connection, eb: EBClient) -> None:
    respx.get(f"{BASE}/aspsps").mock(
        return_value=httpx.Response(
            200,
            json={
                "aspsps": [
                    {"name": "Mock ASPSP", "country": "PL", "maximum_consent_validity": 15552000}
                ]
            },
        )
    )
    respx.get(f"{BASE}/application").mock(
        return_value=httpx.Response(200, json={"redirect_urls": ["https://example.org/cb"]})
    )
    auth = respx.post(f"{BASE}/auth").mock(
        return_value=httpx.Response(200, json={"url": "https://bank.test/sca"})
    )
    url = await sessions.start_auth(conn, eb, aspsp_name="Mock")
    assert url == "https://bank.test/sca"
    body = json.loads(auth.calls.last.request.content)
    assert body["redirect_url"] == "https://example.org/cb"
    pending = sessions.pending_auth(conn)
    assert pending is not None and pending["aspsp"] == "Mock ASPSP"

    with pytest.raises(EBAuthError):  # obcy state
        await sessions.finish_auth(conn, eb, "https://example.org/cb?code=c&state=obcy")

    respx.post(f"{BASE}/sessions").mock(return_value=httpx.Response(200, json=SESSION))
    query = urlencode({"code": "c-1", "state": pending["state"]})
    record = await sessions.finish_auth(conn, eb, f"https://example.org/cb?{query}")
    assert record.session_id == SESSION["session_id"]
    assert sessions.pending_auth(conn) is None


async def test_finish_without_start(conn: db.sqlite3.Connection, eb: EBClient) -> None:
    with pytest.raises(sessions.SessionError, match="Połącz bank"):
        await sessions.finish_auth(conn, eb, "kod")
