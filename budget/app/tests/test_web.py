"""Panel: Ingress (allowlista, prefiks, cache), ekrany i akcje — klientem ASGI."""

from __future__ import annotations

import json
import re
import stat
from collections.abc import AsyncIterator
from pathlib import Path
from typing import NoReturn
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from budget import __version__, ledger, sessions
from budget.eb_models import SessionResponse
from budget.ha_client import HAClient
from budget.service import Service
from budget.settings import Settings
from budget.storage import db
from budget.web.app import create_app, fmt_date, fmt_money

from .conftest import BASE

FIXTURES = Path(__file__).parent / "fixtures"
SESSION = json.loads((FIXTURES / "eb_mock_session.json").read_text(encoding="utf-8"))
PROXY = ("172.30.32.2", 50000)
INGRESS = "/api/hassio_ingress/tok123"


@pytest.fixture
def service(tmp_path: Path) -> Service:
    settings = Settings(
        eb_application_id="app-kid-1",
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        eb_base_url=BASE,
    )
    return Service(settings, db.connect(":memory:"), HAClient(None), tz=ZoneInfo("Europe/Warsaw"))


def _client(
    service: Service, *, peer: tuple[str, int] = PROXY, dev: bool = False
) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=create_app(service, dev=dev), client=peer)
    return httpx.AsyncClient(
        transport=transport, base_url="http://addon", headers={"X-Ingress-Path": INGRESS}
    )


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


def _write_key(service: Service, private_pem: bytes) -> None:
    path = service.settings.private_key_path
    path.parent.mkdir(parents=True)
    path.write_bytes(private_pem)


def test_fmt_money() -> None:
    assert fmt_money("-1234.5", "PLN") == "−1 234,50 zł"
    assert fmt_money("0", "EUR") == "0,00 €"
    assert fmt_money("1000000", "USD") == "1 000 000,00 USD"
    assert fmt_money(None) == "—"


def test_fmt_date() -> None:
    assert fmt_date("2026-10-01") == "01.10.2026"
    assert fmt_date(None) == "—"
    assert fmt_date("zła") == "zła"


async def test_allowlist(service: Service) -> None:
    async with _client(service, peer=("192.168.0.10", 1)) as c:
        assert (await c.get("/")).status_code == 403
    async with _client(service, peer=("192.168.0.10", 1), dev=True) as c:
        assert (await c.get("/")).status_code == 200


async def test_ingress_prefix_and_cache(client: httpx.AsyncClient) -> None:
    r = await client.get("/")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert f'href="{INGRESS}/bank"' in r.text
    assert f'src="{INGRESS}/static/htmx.min.js?v={__version__}"' in r.text
    assert f"v{__version__}" in r.text
    css = await client.get("/static/app.css")
    assert css.status_code == 200 and "immutable" in css.headers["cache-control"]


async def test_all_pages_render_empty(client: httpx.AsyncClient) -> None:
    for path in ("/", "/status", "/bank", "/import", "/accounts", "/transactions", "/healthz"):
        r = await client.get(path)
        assert r.status_code == 200, path
    assert "Brak konfiguracji" not in (await client.get("/status")).text  # tylko komunikat o kluczu
    assert "klucz prywatny" in (await client.get("/status")).text


async def test_key_upload(client: httpx.AsyncClient, service: Service, private_pem: bytes) -> None:
    r = await client.post("/bank/key", files={"file": ("x.pem", b"nie klucz")})
    assert r.status_code == 303 and r.headers["location"] == f"{INGRESS}/bank"
    assert "To nie jest klucz" in (await client.get("/bank")).text
    r = await client.post("/bank/key", files={"file": ("k.pem", private_pem)})
    path = service.settings.private_key_path
    assert path.read_bytes() == private_pem
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert service.missing_config() == []


@respx.mock
async def test_session_import_and_pages_with_data(
    client: httpx.AsyncClient, service: Service, private_pem: bytes
) -> None:
    _write_key(service, private_pem)
    respx.get(f"{BASE}/sessions/{SESSION['session_id']}").mock(
        return_value=httpx.Response(
            200,
            json={"status": "AUTHORIZED", "access": {"valid_until": "2027-03-30T10:57:35Z"}},
        )
    )
    file = json.dumps(SESSION).encode()
    r = await client.post("/bank/session", files={"file": ("s.json", file)})
    assert r.status_code == 303
    page = (await client.get("/bank")).text
    assert "Sesja przeniesiona" in page and "Mock ASPSP" in page
    assert not re.search(r"PL\d{26}", page)  # tylko zamaskowane IBAN-y
    status = (await client.get("/status")).text
    assert "AUTHORIZED" in status


@respx.mock
async def test_sync_from_panel_sends_psu(
    client: httpx.AsyncClient, service: Service, private_pem: bytes
) -> None:
    _write_key(service, private_pem)
    sessions.store_session(
        service.conn,
        SessionResponse.from_api({**SESSION, "accounts": [SESSION["accounts"][2]]}),
    )
    uid = SESSION["accounts"][2]["uid"]
    respx.get(f"{BASE}/accounts/{uid}/balances").mock(
        return_value=httpx.Response(200, json={"balances": []})
    )
    tx = respx.get(f"{BASE}/accounts/{uid}/transactions").mock(
        return_value=httpx.Response(200, json={"transactions": []})
    )
    r = await client.post("/sync", headers={"X-Forwarded-For": "10.1.2.3", "User-Agent": "HA-App"})
    assert r.status_code == 303
    assert tx.calls.last.request.headers["Psu-Ip-Address"] == "10.1.2.3"
    assert tx.calls.last.request.headers["Psu-User-Agent"] == "HA-App"
    page = (await client.get("/status")).text
    assert "Synchronizacja: ok" in page


async def test_sync_without_config(client: httpx.AsyncClient) -> None:
    await client.post("/sync")
    assert "Brak konfiguracji" in (await client.get("/status")).text


async def test_csv_import_map_accounts_transactions(
    client: httpx.AsyncClient, service: Service
) -> None:
    r = await client.post(
        "/import", files={"file": ("h.csv", (FIXTURES / "millenet_sample.csv").read_bytes())}
    )
    assert r.status_code == 303
    page = (await client.get("/import")).text
    assert "Zaimportowano" in page and "Raport księgi" in page
    bad = await client.post("/import", files={"file": ("x.csv", b"a;b\n1;2\n")})
    assert bad.status_code == 303
    assert "nie wygląda na eksport" in (await client.get("/import")).text

    # numer karty bez konta → ręczne przypisanie do konta karty
    conn = service.conn
    unmapped = conn.execute("SELECT DISTINCT number FROM csv_row WHERE status = 'unmapped'")
    numbers = [r[0] for r in unmapped]
    if numbers:
        conn.execute("INSERT INTO account (kind, currency, created_at) VALUES ('card', 'PLN', 'x')")
        card = conn.execute("SELECT id FROM account WHERE kind = 'card'").fetchone()[0]
        await client.post("/import/map", data={"number": numbers[0], "account_id": card})
        left = conn.execute(
            "SELECT count(*) FROM csv_row WHERE number = ? AND status = 'unmapped'",
            (numbers[0],),
        ).fetchone()[0]
        assert left == 0
    r = await client.post("/import/map", data={"number": "obcy", "account_id": 999})
    assert "Nieznany numer" in (await client.get("/import")).text

    await client.post("/accounts/1", data={"display_name": "Główne", "include_in_budget": "on"})
    assert "Główne" in (await client.get("/accounts")).text
    await client.post("/accounts/1", data={"display_name": ""})
    assert conn.execute("SELECT include_in_budget FROM account WHERE id = 1").fetchone()[0] == 0

    all_rows = (await client.get("/transactions")).text
    assert "strona 1 z" in all_rows or "brak transakcji" not in all_rows
    filtered = await client.get(
        "/transactions", params={"q": "100%_\\", "date_from": "zła-data", "account": 1}
    )
    assert filtered.status_code == 200 and "Nic nie pasuje do" in filtered.text
    page2 = await client.get("/transactions", params={"page": 2})
    assert page2.status_code == 200


async def test_status_reconcile_base_button(service: Service) -> None:
    from budget import ledger

    from .test_ledger import CARD_IBAN, _itbd, account

    with ledger.transaction(service.conn):
        card = ledger.upsert_eb_account(service.conn, account("u-card", CARD_IBAN, "Visa"))
    _itbd(service.conn, card, "0.00", "2026-10-01T07:00:00+00:00")
    _itbd(service.conn, card, "50.00", "2026-10-05T07:00:00+00:00")
    async with _client(service) as client:
        page = (await client.get("/status")).text
        assert "W DRODZE" in page or "ROZBIEŻNOŚĆ" in page
        assert f'action="{INGRESS}/status/reconcile-base"' in page
        r = await client.post("/status/reconcile-base", data={"account_id": str(card)})
        assert r.status_code == 303
        page = (await client.get("/status")).text
        assert "baza kontroli salda od 2026-10-05T07:00" in page
        assert f"#{card}: OK" in page and "/status/reconcile-base" not in page
        r = await client.post("/status/reconcile-base", data={"account_id": "999"})
        assert "Brak migawki" in (await client.get("/status")).text


async def test_accounts_page_skips_balance_checks(
    client: httpx.AsyncClient, service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Konta pokazują tylko listę kont — bez kosztownego uzgodnienia sald z raportu księgi."""
    service.inbox()  # dzwonek zapamiętuje uzgodnienie (BalanceMemo), więc nie liczy go ponownie

    def forbidden(*_: object) -> NoReturn:
        raise AssertionError("ekran Konta nie powinien uzgadniać sald")

    monkeypatch.setattr(ledger, "check_balances", forbidden)
    assert (await client.get("/accounts")).status_code == 200


async def test_import_page_reuses_balance_checks(
    client: httpx.AsyncClient, service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Import pokazuje uzgodnienie sald z pamięci dzwonka zamiast liczyć je od nowa."""
    service.inbox()  # rozgrzewa BalanceMemo

    def forbidden(*_: object) -> NoReturn:
        raise AssertionError("ekran Import nie powinien uzgadniać sald od nowa")

    monkeypatch.setattr(ledger, "check_balances", forbidden)
    assert (await client.get("/import")).status_code == 200
