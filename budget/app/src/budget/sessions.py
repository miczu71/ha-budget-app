"""Sesje Enable Banking w bazie add-onu: import sesji z CLI i autoryzacja (SCA) z panelu.

Szczegóły kont (IBAN, waluta, produkt) zwraca tylko `POST /sessions`, dlatego sesja z CLI
przechodzi do add-onu jako cały plik `sessions/<id>.json`. `GET /sessions/{id}` (zapytanie do
Enable Banking, nie do banku — bez limitu PSD2) potwierdza, że jest wciąż aktywna.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import ValidationError

from budget import ledger
from budget.eb_client import EBClient, EBError, find_aspsp, parse_redirect
from budget.eb_models import Account, SessionResponse
from budget.storage.db import kv_get, kv_set, now_iso

ACTIVE = "AUTHORIZED"
PENDING_AUTH_KEY = "pending_auth"


class SessionError(Exception):
    """Komunikat dla użytkownika panelu."""


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    aspsp: str
    valid_until: datetime
    status: str
    checked_at: str | None
    accounts: list[Account]

    @property
    def active(self) -> bool:
        return self.status == ACTIVE

    def days_left(self, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        return max((self.valid_until - now).days, 0)


def parse_session_file(data: bytes) -> SessionResponse:
    try:
        raw = json.loads(data.decode("utf-8-sig"))
        if not isinstance(raw, dict):
            raise TypeError("oczekiwany obiekt JSON")
        return SessionResponse.from_api(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SessionError("to nie jest plik JSON sesji (sessions/<id>.json z CLI)") from exc
    except (ValidationError, TypeError) as exc:
        raise SessionError(
            "plik nie wygląda na odpowiedź POST /sessions (brak session_id, kont albo access)"
        ) from exc


def store_session(
    conn: sqlite3.Connection,
    session: SessionResponse,
    *,
    status: str = ACTIVE,
    valid_until: datetime | None = None,
) -> SessionRecord:
    """Zapis sesji jako bieżącej (poprzednie zostają w historii) + konta z aliasami."""
    until = (valid_until or session.access.valid_until).astimezone(UTC)
    with ledger.transaction(conn):
        for acc in session.accounts:
            ledger.upsert_eb_account(conn, acc, bank=session.aspsp.name)
        # bieżąca jest jedna sesja na bank — sesje innych banków zostają nietknięte
        conn.execute("UPDATE eb_session SET is_current = 0 WHERE aspsp = ?", (session.aspsp.name,))
        conn.execute(
            "INSERT INTO eb_session (session_id, aspsp, valid_until, created_at, raw_json, "
            "status, is_current, checked_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?) "
            "ON CONFLICT (session_id) DO UPDATE SET valid_until = excluded.valid_until, "
            "raw_json = excluded.raw_json, status = excluded.status, is_current = 1, "
            "checked_at = excluded.checked_at",
            (
                session.session_id,
                session.aspsp.name,
                until.isoformat(timespec="seconds"),
                now_iso(),
                json.dumps(session.raw, ensure_ascii=False),
                status,
                now_iso(),
            ),
        )
    record = current(conn, session.aspsp.name)
    assert record is not None
    return record


def _record(row: sqlite3.Row) -> SessionRecord:
    raw: dict[str, Any] = json.loads(row["raw_json"] or "{}")
    return SessionRecord(
        session_id=row["session_id"],
        aspsp=row["aspsp"],
        valid_until=datetime.fromisoformat(row["valid_until"]),
        status=row["status"],
        checked_at=row["checked_at"],
        accounts=[Account.from_api(a) for a in raw.get("accounts", [])],
    )


def current_all(conn: sqlite3.Connection) -> list[SessionRecord]:
    """Bieżące sesje wszystkich banków (po nazwie banku)."""
    rows = conn.execute("SELECT * FROM eb_session WHERE is_current = 1 ORDER BY aspsp").fetchall()
    return [_record(r) for r in rows]


def current(conn: sqlite3.Connection, aspsp: str | None = None) -> SessionRecord | None:
    """Bieżąca sesja banku `aspsp` (bez wielkości liter).

    Bez nazwy: sesja najpilniejsza — nieaktywna, a w razie remisu ta, która wygasa pierwsza
    (alerty i encja zgody pokazują najgorszy przypadek).
    """
    records = current_all(conn)
    if aspsp is not None:
        records = [r for r in records if r.aspsp.casefold() == aspsp.casefold()]
    if not records:
        return None
    return min(records, key=lambda r: (r.active, r.valid_until))


def set_status(conn: sqlite3.Connection, session_id: str, status: str) -> None:
    conn.execute(
        "UPDATE eb_session SET status = ?, checked_at = ? WHERE session_id = ?",
        (status, now_iso(), session_id),
    )


async def refresh_status(conn: sqlite3.Connection, eb: EBClient) -> SessionRecord | None:
    """Status bieżących sesji wszystkich banków z `GET /sessions/{id}` (bez limitu PSD2).

    Zwraca najpilniejszą sesję (jak `current`). Błąd jednego banku nie pomija pozostałych:
    pierwszy wyjątek idzie dalej dopiero po sprawdzeniu reszty.
    """
    first_error: Exception | None = None
    for record in current_all(conn):
        try:
            info = await eb.get_session(record.session_id)
        except (EBError, httpx.HTTPError) as exc:
            first_error = first_error or exc
            continue
        conn.execute(
            "UPDATE eb_session SET status = ?, valid_until = ?, checked_at = ? "
            "WHERE session_id = ?",
            (
                info.status,
                info.access.valid_until.astimezone(UTC).isoformat(timespec="seconds"),
                now_iso(),
                record.session_id,
            ),
        )
    if first_error is not None:
        raise first_error
    return current(conn)


async def import_session_file(conn: sqlite3.Connection, eb: EBClient, data: bytes) -> SessionRecord:
    """Przeniesienie sesji z CLI bez nowego SCA."""
    session = parse_session_file(data)
    info = await eb.get_session(session.session_id)
    if info.status != ACTIVE:
        raise SessionError(f"sesja ma status {info.status} — potrzebna nowa autoryzacja w banku")
    return store_session(conn, session, status=info.status, valid_until=info.access.valid_until)


# --- autoryzacja (SCA) z panelu ----------------------------------------------------------------


async def start_auth(
    conn: sqlite3.Connection,
    eb: EBClient,
    *,
    aspsp_name: str,
    country: str = "PL",
    redirect_url: str | None = None,
) -> str:
    """`POST /auth` → link do banku; `state` czeka w bazie na wklejony adres zwrotny.

    Naraz trwa jedna autoryzacja (jeden bank); nowy start zastępuje poprzedni `pending_auth`.
    """
    aspsp = find_aspsp(await eb.get_aspsps(country), aspsp_name, country)
    redirect = redirect_url or next(iter((await eb.get_application()).redirect_urls), None)
    if not redirect:
        raise SessionError("aplikacja Enable Banking nie ma adresu przekierowania (redirect URL)")
    auth, state, valid_until = await eb.start_auth(aspsp, redirect)
    kv_set(
        conn,
        PENDING_AUTH_KEY,
        {"state": state, "aspsp": aspsp.name, "valid_until": valid_until.isoformat()},
    )
    return auth.url


def pending_auth(conn: sqlite3.Connection) -> dict[str, Any] | None:
    value = kv_get(conn, PENDING_AUTH_KEY)
    return value if isinstance(value, dict) else None


async def finish_auth(conn: sqlite3.Connection, eb: EBClient, pasted: str) -> SessionRecord:
    """Wklejony adres zwrotny (albo sam kod) → `POST /sessions` → nowa bieżąca sesja tego banku."""
    pending = pending_auth(conn)
    if pending is None:
        raise SessionError("brak rozpoczętej autoryzacji — najpierw „Połącz bank”")
    result = parse_redirect(pasted, expected_state=pending["state"])
    session = await eb.create_session(result.code)
    record = store_session(conn, session)
    kv_set(conn, PENDING_AUTH_KEY, None)
    return record
