"""Synchronizacja z bankiem: salda + transakcje dla kont bieżącej sesji, z limitem PSD2.

Limit: bank może odmówić więcej niż 4 zapytań na konto na dobę bez obecności użytkownika
(SPEC §2.3). Licznik (`api_request`) liczy każde zapytanie osobno per endpoint — także każdą
stronę transakcji — i nie wyśle zapytania ponad limit. Zapytania z nagłówkami PSU (użytkownik
w panelu) liczą się osobno i nie są ograniczane.

Okno transakcji: od ostatniego księgowania konta − `OVERLAP_DAYS` (zwykle jedna strona), nie
dalej niż `API_HISTORY_DAYS` wstecz (Millennium i tak oddaje tylko 90 dni). Okno, którego nie
da się pobrać w całości w limicie, nie trafia do księgi — inaczej powstałaby luka, której
okno przyrostowe już nie wypełni; zostaje status `partial` i prośba o synchronizację z panelu.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import httpx

from budget import eb_ingest, ledger, sessions
from budget.eb_client import EBClient, EBError, EBRateLimited, EBSessionExpired, PsuHeaders
from budget.eb_models import Transaction
from budget.storage.db import now_iso

log = logging.getLogger(__name__)

DAILY_LIMIT = 4
OVERLAP_DAYS = 10
API_HISTORY_DAYS = 90
FAILURES_TO_ALERT = 3

Endpoint = Literal["balances", "transactions"]
Status = Literal["ok", "partial", "error", "rate_limited", "expired", "no_session"]


class RequestBudget:
    """Licznik zapytań do banku na dany dzień lokalny."""

    def __init__(self, conn: sqlite3.Connection, day: date, limit: int = DAILY_LIMIT) -> None:
        self._conn = conn
        self.day = day.isoformat()
        self.limit = limit

    def used(self, account_id: int, endpoint: Endpoint, *, psu: bool = False) -> int:
        row = self._conn.execute(
            "SELECT n FROM api_request WHERE day = ? AND account_id = ? AND endpoint = ? "
            "AND psu = ?",
            (self.day, account_id, endpoint, int(psu)),
        ).fetchone()
        return int(row["n"]) if row else 0

    def allows(self, account_id: int, endpoint: Endpoint, *, psu: bool) -> bool:
        return psu or self.used(account_id, endpoint) < self.limit

    def record(self, account_id: int, endpoint: Endpoint, *, psu: bool) -> None:
        self._conn.execute(
            "INSERT INTO api_request (day, account_id, endpoint, psu, n) VALUES (?, ?, ?, ?, 1) "
            "ON CONFLICT (day, account_id, endpoint, psu) DO UPDATE SET n = n + 1",
            (self.day, account_id, endpoint, int(psu)),
        )


@dataclass
class AccountResult:
    account_id: int
    balances: bool = False
    pages: int = 0
    window_from: date | None = None
    complete: bool = False
    new: int = 0
    updated: int = 0
    note: str = ""


@dataclass
class SyncResult:
    status: Status
    trigger: str
    started_at: str
    finished_at: str = ""
    new: int = 0
    updated: int = 0
    requests: int = 0
    detail: str = ""
    accounts: list[AccountResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def window_start(conn: sqlite3.Connection, account_id: int, today: date, *, full: bool) -> date:
    oldest = today - timedelta(days=API_HISTORY_DAYS)
    if full:
        return oldest
    row = conn.execute(
        "SELECT max(booking_date) AS d FROM txn WHERE account_id = ? AND status = 'BOOK'",
        (account_id,),
    ).fetchone()
    if row["d"] is None:
        return oldest
    return max(date.fromisoformat(row["d"]) - timedelta(days=OVERLAP_DAYS), oldest)


async def sync(
    conn: sqlite3.Connection,
    eb: EBClient,
    *,
    tz: ZoneInfo,
    trigger: str = "schedule",
    psu: PsuHeaders | None = None,
    full: bool = False,
    now: datetime | None = None,
) -> SyncResult:
    """Jeden przebieg synchronizacji; wynik zapisany w `sync_log`."""
    now = (now or datetime.now(tz)).astimezone(tz)
    today = now.date()
    result = SyncResult(status="ok", trigger=trigger, started_at=now_iso())
    record = sessions.current(conn)
    if record is None or not record.active:
        result.status = "no_session"
        result.detail = "brak połączenia z bankiem" if record is None else f"sesja {record.status}"
        return _log(conn, result)

    budget = RequestBudget(conn, today)
    with_psu = psu is not None
    headers = psu.as_headers() if psu else None
    fetched_at = now_iso()
    try:
        for acc in record.accounts:
            account_id = ledger.account_by_alias(conn, "eb_uid", acc.uid)
            if account_id is None:  # konto spoza księgi — sesja zapisana bez niego
                continue
            res = AccountResult(account_id)
            result.accounts.append(res)
            # --- salda
            if budget.allows(account_id, "balances", psu=with_psu):
                budget.record(account_id, "balances", psu=with_psu)
                result.requests += 1
                balances = await eb.get_balances(acc.uid, psu_headers=headers)
                ledger.ingest_balances(conn, account_id, balances, fetched_at=fetched_at)
                res.balances = True
            else:
                res.note = "salda: limit dzienny"
            # --- transakcje
            res.window_from = window_start(conn, account_id, today, full=full)
            if not budget.allows(account_id, "transactions", psu=with_psu):
                res.note = _join(res.note, "transakcje: limit dzienny")
                continue
            collected: list[Transaction] = []
            budget.record(account_id, "transactions", psu=with_psu)
            result.requests += 1
            async for page in eb.iter_transaction_pages(
                acc.uid, res.window_from, psu_headers=headers
            ):
                res.pages += 1
                collected.extend(page.transactions)
                if not page.continuation_key:
                    res.complete = True
                    break
                if not budget.allows(account_id, "transactions", psu=with_psu):
                    break
                budget.record(account_id, "transactions", psu=with_psu)
                result.requests += 1
            if not res.complete:
                res.note = _join(res.note, "okno niepełne (limit) — pominięte")
                continue
            kind = conn.execute("SELECT kind FROM account WHERE id = ?", (account_id,)).fetchone()[
                "kind"
            ]
            stats = ledger.ingest_api(
                conn,
                account_id,
                eb_ingest.convert(collected, card_account=kind == "card"),
                fetched_at=fetched_at,
                date_from=res.window_from,
            )
            res.new, res.updated = stats.new, stats.updated
            result.new += stats.new
            result.updated += stats.updated
    except EBSessionExpired as exc:
        sessions.set_status(conn, record.session_id, "EXPIRED")
        result.status, result.detail = "expired", f"sesja wygasła lub cofnięta ({exc.code})"
    except EBRateLimited as exc:
        result.status, result.detail = "rate_limited", f"bank odrzucił: limit zapytań ({exc.code})"
    except EBError as exc:
        result.status, result.detail = "error", f"błąd API {exc.status} {exc.code}"
    except httpx.HTTPError as exc:
        result.status, result.detail = "error", f"błąd sieci: {type(exc).__name__}"
    if result.status == "ok" and any(r.note for r in result.accounts):
        result.status = "partial"
    if result.status == "ok" or result.status == "partial":
        result.detail = _join(
            result.detail,
            "; ".join(f"#{r.account_id}: {r.note}" for r in result.accounts if r.note),
        )
    return _log(conn, result)


def _join(a: str, b: str) -> str:
    return f"{a}; {b}" if a and b else a or b


def _log(conn: sqlite3.Connection, result: SyncResult) -> SyncResult:
    result.finished_at = now_iso()
    conn.execute(
        "INSERT INTO sync_log (started_at, finished_at, status, detail, trigger, new_txn, "
        "updated_txn, requests) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            result.started_at,
            result.finished_at,
            result.status,
            result.detail,
            result.trigger,
            result.new,
            result.updated,
            result.requests,
        ),
    )
    log.info(
        "Synchronizacja (%s): %s, nowych %d, zmienionych %d, zapytań %d%s",
        result.trigger,
        result.status,
        result.new,
        result.updated,
        result.requests,
        f" — {result.detail}" if result.detail else "",
    )
    return result


def consecutive_failures(conn: sqlite3.Connection) -> int:
    """Ile ostatnich przebiegów z rzędu się nie udało (`partial` i `no_session` nie liczą się)."""
    count = 0
    for row in conn.execute(
        "SELECT status FROM sync_log WHERE status NOT IN ('no_session') ORDER BY id DESC LIMIT 20"
    ):
        if row["status"] in ("ok", "partial"):
            break
        count += 1
    return count


def recent(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def requests_today(conn: sqlite3.Connection, day: date) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT account_id, endpoint, psu, n FROM api_request WHERE day = ? "
        "ORDER BY account_id, endpoint, psu",
        (day.isoformat(),),
    ).fetchall()


def max_requests_today(conn: sqlite3.Connection, day: date) -> int:
    """Najwyżej obciążona para (konto, endpoint) bez PSU — do encji diagnostycznej."""
    row = conn.execute(
        "SELECT max(n) AS n FROM api_request WHERE day = ? AND psu = 0", (day.isoformat(),)
    ).fetchone()
    return int(row["n"] or 0)


# --- harmonogram -------------------------------------------------------------------------------


def next_run(now: datetime, times: tuple[str, ...]) -> datetime:
    """Najbliższa godzina z `sync_times` (strefa `now`) ściśle po `now`."""
    candidates = []
    for offset in (0, 1):
        day = now.date() + timedelta(days=offset)
        for t in times:
            hh, mm = (int(x) for x in t.split(":"))
            at = datetime(day.year, day.month, day.day, hh, mm, tzinfo=now.tzinfo)
            if at > now:
                candidates.append(at)
    return min(candidates)
