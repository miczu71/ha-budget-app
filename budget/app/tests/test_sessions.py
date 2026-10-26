"""Sesje EB w bazie add-onu: import z CLI (bez SCA) i autoryzacja z panelu."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest
import respx

from budget import sessions
from budget.eb_client import EBAuthError, EBClient
from budget.eb_models import SessionResponse
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


# --- wielobankowość (M32 E1): sesja per bank --------------------------------------------------

BANK_B = "Bank Drugi"


def _session_b() -> SessionResponse:
    """Druga sesja: inny bank, inne konta (neutralne dane testowe)."""
    acc = {
        **SESSION["accounts"][2],
        "uid": "b-uid-1",
        "account_id": {"iban": "PL10105000997603123456789123", "other": None},
        "identification_hash": "hash-b-1",
        "product": "Konto Premiowe",
        "name": "Jan Testowy",
    }
    return SessionResponse.from_api(
        {
            **SESSION,
            "session_id": "s-b",
            "aspsp": {"name": BANK_B, "country": "PL"},
            "accounts": [acc],
        }
    )


def test_two_banks_coexist(conn: sqlite3.Connection) -> None:
    a = sessions.store_session(conn, SessionResponse.from_api(SESSION))
    b = sessions.store_session(conn, _session_b())
    assert (a.aspsp, b.aspsp) == ("Mock ASPSP", BANK_B)
    cur_a = sessions.current(conn, "Mock ASPSP")
    cur_b = sessions.current(conn, BANK_B)
    assert cur_a is not None and cur_a.session_id == SESSION["session_id"]
    assert cur_b is not None and cur_b.session_id == "s-b"
    assert {r.aspsp for r in sessions.current_all(conn)} == {"Mock ASPSP", BANK_B}
    assert sessions.current(conn, "Nieznany") is None


def test_new_session_replaces_only_its_bank(conn: sqlite3.Connection) -> None:
    sessions.store_session(conn, SessionResponse.from_api(SESSION))
    sessions.store_session(conn, _session_b())
    renewed = SessionResponse.from_api({**SESSION, "session_id": "s-a2"})
    sessions.store_session(conn, renewed)
    cur_a, cur_b = sessions.current(conn, "Mock ASPSP"), sessions.current(conn, BANK_B)
    assert cur_a is not None and cur_a.session_id == "s-a2"
    assert cur_b is not None and cur_b.session_id == "s-b"
    assert conn.execute("SELECT count(*) FROM eb_session").fetchone()[0] == 3


def test_current_without_bank_is_most_urgent(conn: sqlite3.Connection) -> None:
    """Bez nazwy banku (alerty, encja zgody): sesja nieaktywna, potem ta, która wygasa pierwsza."""
    assert sessions.current(conn) is None
    sessions.store_session(conn, SessionResponse.from_api(SESSION))  # ważna do 2027-03-30
    sessions.store_session(conn, _session_b(), valid_until=datetime(2027, 1, 1, tzinfo=UTC))
    worst = sessions.current(conn)
    assert worst is not None and worst.aspsp == BANK_B
    sessions.set_status(conn, SESSION["session_id"], "EXPIRED")
    worst = sessions.current(conn)
    assert worst is not None and worst.aspsp == "Mock ASPSP" and not worst.active


def test_accounts_remember_their_bank(conn: sqlite3.Connection) -> None:
    sessions.store_session(conn, SessionResponse.from_api(SESSION))
    sessions.store_session(conn, _session_b())
    rows = conn.execute(
        "SELECT a.bank, count(*) AS n FROM account a GROUP BY a.bank ORDER BY a.bank"
    ).fetchall()
    assert [(r["bank"], r["n"]) for r in rows] == [(BANK_B, 1), ("Mock ASPSP", 2)]


def test_legacy_database_is_migrated_without_loss(monkeypatch: pytest.MonkeyPatch) -> None:
    """Produkcja: jedna sesja is_current=1 i konta bez kolumny banku — migracja dopisuje bank."""
    conn = db.connect(":memory:")
    sessions.store_session(conn, SessionResponse.from_api(SESSION))
    conn.execute("ALTER TABLE account DROP COLUMN bank")  # stan sprzed migracji 029
    conn.execute("PRAGMA user_version = 28")
    assert db.migrate(conn) == db.schema_version(conn) >= 29
    banks = {r[0] for r in conn.execute("SELECT bank FROM account")}
    assert banks == {"Mock ASPSP"}
    legacy = sessions.current(conn)
    assert legacy is not None and legacy.session_id == SESSION["session_id"] and legacy.active
    assert sessions.current(conn, "Mock ASPSP") == legacy


@respx.mock
async def test_refresh_status_all_banks(conn: sqlite3.Connection, eb: EBClient) -> None:
    sessions.store_session(conn, SessionResponse.from_api(SESSION))
    sessions.store_session(conn, _session_b())
    respx.get(f"{BASE}/sessions/{SESSION['session_id']}").mock(return_value=_info())
    respx.get(f"{BASE}/sessions/s-b").mock(return_value=_info("REVOKED"))
    await sessions.refresh_status(conn, eb)
    cur_a, cur_b = sessions.current(conn, "Mock ASPSP"), sessions.current(conn, BANK_B)
    assert cur_a is not None and cur_a.active
    assert cur_b is not None and cur_b.status == "REVOKED"


@respx.mock
async def test_auth_flow_second_bank_keeps_first(conn: sqlite3.Connection, eb: EBClient) -> None:
    sessions.store_session(conn, SessionResponse.from_api(SESSION))
    respx.get(f"{BASE}/aspsps").mock(
        return_value=httpx.Response(
            200,
            json={"aspsps": [{"name": BANK_B, "country": "PL", "maximum_consent_validity": 1}]},
        )
    )
    respx.get(f"{BASE}/application").mock(
        return_value=httpx.Response(200, json={"redirect_urls": ["https://example.org/cb"]})
    )
    respx.post(f"{BASE}/auth").mock(
        return_value=httpx.Response(200, json={"url": "https://bank-b.test/sca"})
    )
    await sessions.start_auth(conn, eb, aspsp_name=BANK_B)
    pending = sessions.pending_auth(conn)
    assert pending is not None and pending["aspsp"] == BANK_B
    respx.post(f"{BASE}/sessions").mock(return_value=httpx.Response(200, json=_session_b().raw))
    query = urlencode({"code": "c-2", "state": pending["state"]})
    record = await sessions.finish_auth(conn, eb, f"https://example.org/cb?{query}")
    assert record.aspsp == BANK_B
    first = sessions.current(conn, "Mock ASPSP")
    assert first is not None and first.session_id == SESSION["session_id"]
