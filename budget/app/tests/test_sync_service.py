"""Synchronizacja: okno przyrostowe, licznik zapytań PSD2 (strony, PSU), błędy, harmonogram."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from budget import sessions, sync_service
from budget.eb_client import EBClient, PsuHeaders
from budget.eb_models import SessionResponse, Transaction
from budget.storage import db

from .conftest import BASE

FIXTURES = Path(__file__).parent / "fixtures"
TZ = ZoneInfo("Europe/Warsaw")
NOW = datetime(2026, 10, 2, 8, 0, tzinfo=TZ)
_SESSION = json.loads((FIXTURES / "eb_mock_session.json").read_text(encoding="utf-8"))
# dwa konta o różnych IBAN-ach (w fixture dwa pierwsze dzielą IBAN)
SESSION = {**_SESSION, "accounts": [_SESSION["accounts"][0], _SESSION["accounts"][2]]}
UID_MAIN, UID_SAV = (a["uid"] for a in SESSION["accounts"])
MAIN_TXNS = json.loads((FIXTURES / "eb_mock_transactions_main.json").read_text())["transactions"]
BOOKED = sum(t["status"] == "BOOK" for t in MAIN_TXNS)  # oczekujące nie liczą się do „nowych”


def _balances(amount: str = "100.00") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "balances": [
                {"balance_amount": {"currency": "PLN", "amount": amount}, "balance_type": t}
                for t in ("ITAV", "ITBD")
            ]
        },
    )


def _page(txns: list[dict[str, object]], key: str | None = None) -> httpx.Response:
    return httpx.Response(200, json={"transactions": txns, "continuation_key": key})


@pytest.fixture
def conn() -> db.sqlite3.Connection:
    c = db.connect(":memory:")
    sessions.store_session(c, SessionResponse.from_api(SESSION))
    return c


def _account(conn: db.sqlite3.Connection, uid: str) -> int:
    row = conn.execute(
        "SELECT account_id FROM account_alias WHERE source = 'eb_uid' AND value = ?", (uid,)
    ).fetchone()
    return int(row[0])


def _mock_ok(main_txns: list[dict[str, object]] | None = None) -> dict[str, respx.Route]:
    return {
        "bal_main": respx.get(f"{BASE}/accounts/{UID_MAIN}/balances").mock(
            return_value=_balances()
        ),
        "bal_sav": respx.get(f"{BASE}/accounts/{UID_SAV}/balances").mock(
            return_value=_balances("5.00")
        ),
        "tx_main": respx.get(f"{BASE}/accounts/{UID_MAIN}/transactions").mock(
            return_value=_page(MAIN_TXNS if main_txns is None else main_txns)
        ),
        "tx_sav": respx.get(f"{BASE}/accounts/{UID_SAV}/transactions").mock(return_value=_page([])),
    }


@respx.mock
async def test_no_session_is_logged(eb: EBClient) -> None:
    conn = db.connect(":memory:")
    result = await sync_service.sync(conn, eb, tz=TZ, now=NOW)
    assert result.status == "no_session"
    assert sync_service.recent(conn)[0]["status"] == "no_session"


@respx.mock
async def test_first_sync_full_window_then_incremental(
    conn: db.sqlite3.Connection, eb: EBClient
) -> None:
    routes = _mock_ok()
    result = await sync_service.sync(conn, eb, tz=TZ, now=NOW)
    assert result.status == "ok", result.detail
    assert result.new == BOOKED and result.requests == 4
    first_from = routes["tx_main"].calls.last.request.url.params["date_from"]
    assert first_from == "2026-07-04"  # dziś − 90 d
    main = _account(conn, UID_MAIN)
    assert (
        conn.execute(
            "SELECT count(*) FROM balance_snapshot WHERE account_id = ?", (main,)
        ).fetchone()[0]
        == 2
    )
    budget = sync_service.RequestBudget(conn, NOW.date())
    assert budget.used(main, "balances") == 1 and budget.used(main, "transactions") == 1

    # drugi przebieg: okno od ostatniego księgowania − 10 dni, nic nowego
    result = await sync_service.sync(conn, eb, tz=TZ, now=NOW)
    assert result.status == "ok" and result.new == 0
    assert routes["tx_main"].calls.last.request.url.params["date_from"] == "2026-09-26"
    log = sync_service.recent(conn)
    assert [r["status"] for r in log] == ["ok", "ok"]
    assert log[0]["requests"] == 4 and log[1]["new_txn"] == BOOKED


@respx.mock
async def test_daily_limit_blocks_requests(conn: db.sqlite3.Connection, eb: EBClient) -> None:
    routes = _mock_ok()
    main = _account(conn, UID_MAIN)
    budget = sync_service.RequestBudget(conn, NOW.date())
    for _ in range(4):
        budget.record(main, "transactions", psu=False)
    result = await sync_service.sync(conn, eb, tz=TZ, now=NOW)
    assert result.status == "partial"
    assert "limit dzienny" in result.detail
    assert not routes["tx_main"].called and routes["bal_main"].called
    assert budget.used(main, "transactions") == 4


@respx.mock
async def test_window_cut_by_limit_is_not_ingested(
    conn: db.sqlite3.Connection, eb: EBClient
) -> None:
    routes = _mock_ok()
    routes["tx_main"].mock(
        side_effect=[_page(MAIN_TXNS[:10], key="k1"), _page(MAIN_TXNS[10:], key=None)]
    )
    main = _account(conn, UID_MAIN)
    budget = sync_service.RequestBudget(conn, NOW.date())
    for _ in range(3):
        budget.record(main, "transactions", psu=False)
    result = await sync_service.sync(conn, eb, tz=TZ, now=NOW)
    assert result.status == "partial" and "niepełne" in result.detail
    assert routes["tx_main"].call_count == 1  # druga strona już ponad limit
    assert conn.execute("SELECT count(*) FROM txn").fetchone()[0] == 0
    assert budget.used(main, "transactions") == 4


@respx.mock
async def test_pages_counted_and_psu_bypasses_limit(
    conn: db.sqlite3.Connection, eb: EBClient
) -> None:
    routes = _mock_ok()
    routes["tx_main"].mock(
        side_effect=[_page(MAIN_TXNS[:10], key="k1"), _page(MAIN_TXNS[10:], key=None)]
    )
    main = _account(conn, UID_MAIN)
    budget = sync_service.RequestBudget(conn, NOW.date())
    for _ in range(4):
        budget.record(main, "transactions", psu=False)
    psu = PsuHeaders(ip_address="10.0.0.2", user_agent="Mozilla/5.0")
    result = await sync_service.sync(conn, eb, tz=TZ, now=NOW, psu=psu, trigger="panel")
    assert result.status == "ok", result.detail
    assert result.new == BOOKED
    sent = routes["tx_main"].calls.last.request.headers
    assert sent["Psu-Ip-Address"] == "10.0.0.2"
    assert budget.used(main, "transactions", psu=True) == 2
    assert budget.used(main, "transactions") == 4
    assert sync_service.max_requests_today(conn, NOW.date()) == 4


@respx.mock
async def test_expired_session(conn: db.sqlite3.Connection, eb: EBClient) -> None:
    respx.get(f"{BASE}/accounts/{UID_MAIN}/balances").mock(
        return_value=httpx.Response(401, json={"code": "EXPIRED_SESSION", "message": "x"})
    )
    result = await sync_service.sync(conn, eb, tz=TZ, now=NOW)
    assert result.status == "expired"
    record = sessions.current(conn)
    assert record is not None and record.status == "EXPIRED"
    # kolejny przebieg nie pyta banku
    assert (await sync_service.sync(conn, eb, tz=TZ, now=NOW)).status == "no_session"


@respx.mock
async def test_rate_limited_and_failure_count(conn: db.sqlite3.Connection, eb: EBClient) -> None:
    respx.get(f"{BASE}/accounts/{UID_MAIN}/balances").mock(
        return_value=httpx.Response(429, json={"code": "ASPSP_RATE_LIMIT_EXCEEDED"})
    )
    for _ in range(3):
        result = await sync_service.sync(conn, eb, tz=TZ, now=NOW)
        assert result.status == "rate_limited"
    assert sync_service.consecutive_failures(conn) == 3
    _mock_ok()
    assert (await sync_service.sync(conn, eb, tz=TZ, now=NOW)).ok
    assert sync_service.consecutive_failures(conn) == 0


@respx.mock
async def test_network_error(conn: db.sqlite3.Connection, eb: EBClient) -> None:
    respx.get(f"{BASE}/accounts/{UID_MAIN}/balances").mock(side_effect=httpx.ConnectTimeout)
    result = await sync_service.sync(conn, eb, tz=TZ, now=NOW)
    assert result.status == "error" and "ConnectTimeout" in result.detail


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 2, 5, 0, tzinfo=TZ), datetime(2026, 10, 2, 6, 30, tzinfo=TZ)),
        (datetime(2026, 10, 2, 6, 30, tzinfo=TZ), datetime(2026, 10, 2, 13, 30, tzinfo=TZ)),
        (datetime(2026, 10, 2, 22, 0, tzinfo=TZ), datetime(2026, 10, 3, 6, 30, tzinfo=TZ)),
    ],
)
def test_next_run(now: datetime, expected: datetime) -> None:
    assert sync_service.next_run(now, ("06:30", "13:30", "21:30")) == expected


def test_next_run_across_dst() -> None:
    # 25.10.2026 zmiana czasu — 06:30 lokalnie, nie przesunięte o godzinę
    at = sync_service.next_run(datetime(2026, 10, 24, 22, 0, tzinfo=TZ), ("06:30",))
    assert at.astimezone(UTC) == datetime(2026, 10, 25, 5, 30, tzinfo=UTC)
    assert at.date() == date(2026, 10, 25)


def _txn(day: str, ref: str) -> dict[str, object]:
    return {
        "entry_reference": f"BOOKED|{ref}|{day}|1",
        "transaction_amount": {"currency": "PLN", "amount": "10.00"},
        "credit_debit_indicator": "DBIT",
        "status": "BOOK",
        "booking_date": day,
        "remittance_information": [f"Sklep {ref}"],
    }


@respx.mock
async def test_bank_ignoring_date_from_stops_when_window_covered(
    conn: db.sqlite3.Connection, eb: EBClient
) -> None:
    """Millennium ignoruje `date_from` i zawsze oddaje 90 dni, najnowsze strony pierwsze."""
    main = _account(conn, UID_MAIN)
    await_first = _mock_ok(main_txns=[_txn("2026-09-25", "a")])
    assert (await sync_service.sync(conn, eb, tz=TZ, now=NOW)).ok  # księga: ostatnie 25.09
    pages = [
        _page([_txn("2026-10-02", "n1"), _txn("2026-09-23", "n2")], key="k1"),  # ≥ 20.09
        _page([_txn("2026-09-19", "o1"), _txn("2026-09-01", "o2")], key="k2"),  # sięga < okna
        _page([_txn("2026-08-01", "o3")], key="k3"),  # nie powinno być pobrane
    ]
    await_first["tx_main"].mock(side_effect=pages)
    result = await sync_service.sync(conn, eb, tz=TZ, now=NOW)
    assert result.status == "ok", result.detail
    assert await_first["tx_main"].call_count == 1 + 2  # pierwszy przebieg + 2 strony
    assert result.accounts[0].window_from == date(2026, 9, 20)
    assert sync_service.RequestBudget(conn, NOW.date()).used(main, "transactions") == 3
    refs = {r[0] for r in conn.execute("SELECT description FROM txn")}
    assert {"Sklep n1", "Sklep n2", "Sklep o1"} <= refs


@respx.mock
async def test_unordered_pages_are_fetched_to_the_end(
    conn: db.sqlite3.Connection, eb: EBClient
) -> None:
    """Bez malejącej kolejności nie wolno kończyć wcześniej — mogłyby zginąć nowsze."""
    routes = _mock_ok(main_txns=[_txn("2026-09-25", "a")])
    assert (await sync_service.sync(conn, eb, tz=TZ, now=NOW)).ok
    routes["tx_main"].mock(
        side_effect=[
            _page([_txn("2026-09-01", "o1")], key="k1"),  # rosnąco: najstarsze pierwsze
            _page([_txn("2026-10-02", "n1")], key=None),
        ]
    )
    result = await sync_service.sync(conn, eb, tz=TZ, now=NOW)
    assert result.ok
    assert routes["tx_main"].call_count == 1 + 2
    assert "Sklep n1" in {r[0] for r in conn.execute("SELECT description FROM txn")}


def _t(day: str) -> Transaction:
    return Transaction.from_api(_txn(day, day))


@pytest.mark.parametrize(
    ("days", "covered"),
    [
        (["2026-10-02", "2026-09-19"], True),  # malejąco i sięga przed okno
        (["2026-10-02", "2026-09-21"], False),  # jeszcze nie sięga
        (["2026-09-19"], False),  # jedna, starsza niż okno — kolejność nieznana
        (["2026-09-01", "2026-10-02", "2026-09-10"], False),  # nie malejąco
        (["2026-09-25", "2026-09-25", "2026-09-19"], True),
        ([], False),
    ],
)
def test_order_check(days: list[str], covered: bool) -> None:
    check = sync_service.OrderCheck(date(2026, 9, 20))
    check.feed([_t(d) for d in days])
    assert check.covered is covered
