import json
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa

from budget.eb_client import (
    EBAuthError,
    EBClient,
    EBError,
    EBRateLimited,
    EBSessionExpired,
    PsuHeaders,
    PsuHeadersIncomplete,
    build_psu_headers,
    find_aspsp,
    parse_redirect,
)
from budget.eb_models import Aspsp

from .conftest import BASE, FakeClock


def _decode(token: str, key: rsa.RSAPrivateKey) -> dict[str, object]:
    claims: dict[str, object] = jwt.decode(
        token,
        key.public_key(),
        algorithms=["RS256"],
        audience="api.enablebanking.com",
        issuer="enablebanking.com",
        options={"verify_exp": False, "verify_iat": False},
    )
    return claims


# --- JWT -----------------------------------------------------------------------


def test_jwt_header_and_claims(eb: EBClient, rsa_key: rsa.RSAPrivateKey, clock: FakeClock) -> None:
    token = eb.token()
    header = jwt.get_unverified_header(token)
    assert header == {"alg": "RS256", "kid": "app-kid-1", "typ": "JWT"}
    claims = _decode(token, rsa_key)
    assert claims["iat"] == int(clock.now)
    assert claims["exp"] == int(clock.now) + 3600


def test_jwt_cached_until_refresh_margin(eb: EBClient, clock: FakeClock) -> None:
    first = eb.token()
    clock.now += 3000
    assert eb.token() == first
    clock.now += 541  # 59 s przed exp → odnowienie
    assert eb.token() != first


def test_ttl_limit(private_pem: bytes) -> None:
    with pytest.raises(ValueError, match="token_ttl"):
        EBClient("k", private_pem, token_ttl=86401)


def test_rejects_non_rsa_key() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    with pytest.raises(ValueError, match="RSA"):
        EBClient("k", pem)


# --- HTTP / błędy --------------------------------------------------------------


@respx.mock
async def test_401_renews_token_and_retries_once(eb: EBClient, clock: FakeClock) -> None:
    eb.token()  # token w cache
    clock.now += 1000  # nadal ważny w cache, ale 401 wymusza nowy (nowe iat)
    route = respx.get(f"{BASE}/application").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json={"name": "x", "kid": "k"})]
    )
    app = await eb.get_application()
    assert app.name == "x"
    assert route.call_count == 2
    first, second = (c.request.headers["Authorization"] for c in route.calls)
    assert first != second


@respx.mock
async def test_401_twice_raises(eb: EBClient) -> None:
    respx.get(f"{BASE}/application").mock(
        return_value=httpx.Response(401, json={"code": "UNAUTHORIZED", "message": "bad jwt"})
    )
    with pytest.raises(EBError) as exc:
        await eb.get_application()
    assert exc.value.status == 401
    assert exc.value.code == "UNAUTHORIZED"


@pytest.mark.parametrize(
    ("status", "body", "exc_type"),
    [
        (429, {"message": "slow down"}, EBRateLimited),
        (400, {"code": "ASPSP_RATE_LIMIT_EXCEEDED", "message": "4/day"}, EBRateLimited),
        (401, {"code": "EXPIRED_SESSION", "message": "expired"}, EBSessionExpired),
        (400, {"code": "PSU_HEADER_NOT_PROVIDED", "message": "psu"}, EBError),
    ],
)
@respx.mock
async def test_error_mapping(
    eb: EBClient, status: int, body: dict[str, str], exc_type: type[EBError]
) -> None:
    respx.get(f"{BASE}/accounts/u1/balances").mock(return_value=httpx.Response(status, json=body))
    with pytest.raises(exc_type) as exc:
        await eb.get_balances("u1")
    assert type(exc.value) is exc_type


@respx.mock
async def test_non_json_error(eb: EBClient) -> None:
    respx.get(f"{BASE}/application").mock(return_value=httpx.Response(502, text="Bad Gateway"))
    with pytest.raises(EBError, match="Bad Gateway"):
        await eb.get_application()


# --- AIS -----------------------------------------------------------------------


@respx.mock
async def test_get_aspsps_and_find(eb: EBClient) -> None:
    route = respx.get(f"{BASE}/aspsps").mock(
        return_value=httpx.Response(
            200,
            json={
                "aspsps": [
                    {
                        "name": "Bank Millennium",
                        "country": "PL",
                        "maximum_consent_validity": 15552000,
                        "required_psu_headers": ["Psu-Ip-Address", "Psu-User-Agent"],
                        "logo": "https://x/logo.png",
                    },
                    {"name": "Millennium Business", "country": "PL"},
                ]
            },
        )
    )
    aspsps = await eb.get_aspsps("PL")
    params = route.calls.last.request.url.params
    assert params["country"] == "PL"
    assert params["service"] == "AIS"
    assert params["psu_type"] == "personal"
    bank = find_aspsp(aspsps, "bank millennium", "pl")
    assert bank.maximum_consent_validity == 15552000
    with pytest.raises(LookupError, match="nie jest jednoznaczny"):
        find_aspsp(aspsps, "Millennium")


@respx.mock
async def test_start_auth_body(eb: EBClient, clock: FakeClock) -> None:
    route = respx.post(f"{BASE}/auth").mock(
        return_value=httpx.Response(200, json={"url": "https://bank/auth", "authorization_id": "a"})
    )
    aspsp = Aspsp(name="Bank Millennium", country="PL", maximum_consent_validity=180 * 86400)
    auth, state, valid_until = await eb.start_auth(aspsp, "https://ha/cb")
    body = json.loads(route.calls.last.request.content)
    assert auth.url == "https://bank/auth"
    assert body["state"] == state and len(state) == 36
    assert body["aspsp"] == {"name": "Bank Millennium", "country": "PL"}
    assert body["redirect_url"] == "https://ha/cb"
    assert body["psu_type"] == "personal"
    assert body["access"]["balances"] is True and body["access"]["transactions"] is True
    expected = datetime.fromtimestamp(clock.now + 180 * 86400 - 3600, UTC)
    assert valid_until == expected
    assert body["access"]["valid_until"] == expected.isoformat(timespec="seconds")
    assert body["access"]["valid_until"].endswith("+00:00")


@respx.mock
async def test_create_session_keeps_raw(eb: EBClient) -> None:
    payload = {
        "session_id": "s-1",
        "aspsp": {"name": "Bank Millennium", "country": "PL"},
        "psu_type": "personal",
        "access": {"valid_until": "2027-03-30T10:00:00+00:00"},
        "accounts": [
            {
                "uid": "u-1",
                "identification_hash": "h-1",
                "account_id": {"iban": "PL61109010140000071219812874"},
                "currency": "PLN",
                "cash_account_type": "CACC",
                "only_once_field": {"x": 1},
            }
        ],
    }
    route = respx.post(f"{BASE}/sessions").mock(return_value=httpx.Response(200, json=payload))
    session = await eb.create_session("the-code")
    assert json.loads(route.calls.last.request.content) == {"code": "the-code"}
    assert session.raw == payload
    assert session.accounts[0].iban == "PL61109010140000071219812874"
    assert session.accounts[0].raw["only_once_field"] == {"x": 1}


@respx.mock
async def test_get_and_delete_session(eb: EBClient) -> None:
    respx.get(f"{BASE}/sessions/s-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "AUTHORIZED",
                "access": {"valid_until": "2027-03-30T10:00:00Z"},
                "accounts": ["u-1"],
            },
        )
    )
    deleted = respx.delete(f"{BASE}/sessions/s-1").mock(return_value=httpx.Response(200))
    info = await eb.get_session("s-1")
    assert info.status == "AUTHORIZED"
    await eb.delete_session("s-1")
    assert deleted.called


@respx.mock
async def test_balances_decimal(eb: EBClient) -> None:
    respx.get(f"{BASE}/accounts/u-1/balances").mock(
        return_value=httpx.Response(
            200,
            json={
                "balances": [
                    {
                        "name": "Dostępne",
                        "balance_amount": {"currency": "PLN", "amount": "1234.56"},
                        "balance_type": "CLAV",
                        "reference_date": "2026-10-01",
                    }
                ]
            },
        )
    )
    (bal,) = await eb.get_balances("u-1")
    assert bal.balance_amount.amount == Decimal("1234.56")
    assert bal.reference_date == date(2026, 10, 1)


def _txn(n: int, indicator: str = "DBIT") -> dict[str, object]:
    return {
        "entry_reference": f"e{n}",
        "transaction_amount": {"currency": "PLN", "amount": f"{n}.10"},
        "credit_debit_indicator": indicator,
        "status": "BOOK",
        "booking_date": "2026-09-0" + str(n),
    }


@respx.mock
async def test_transactions_paginate_until_empty_key(eb: EBClient) -> None:
    route = respx.get(f"{BASE}/accounts/u-1/transactions").mock(
        side_effect=[
            httpx.Response(200, json={"transactions": [_txn(1)], "continuation_key": "k1"}),
            httpx.Response(200, json={"transactions": [_txn(2)], "continuation_key": "k2"}),
            httpx.Response(200, json={"transactions": [_txn(3)], "continuation_key": ""}),
        ]
    )
    txns = [t async for t in eb.iter_transactions("u-1", date(2026, 7, 1), date(2026, 9, 30))]
    assert [t.entry_reference for t in txns] == ["e1", "e2", "e3"]
    keys = [c.request.url.params.get("continuation_key") for c in route.calls]
    assert keys == [None, "k1", "k2"]
    first = route.calls[0].request.url.params
    assert first["date_from"] == "2026-07-01" and first["date_to"] == "2026-09-30"


@respx.mock
async def test_pagination_loop_guard(eb: EBClient) -> None:
    respx.get(f"{BASE}/accounts/u-1/transactions").mock(
        return_value=httpx.Response(200, json={"transactions": [], "continuation_key": "same"})
    )
    with pytest.raises(EBError, match="continuation_key"):
        async for _ in eb.iter_transactions("u-1", date(2026, 7, 1)):
            pass


@respx.mock
async def test_psu_headers_sent(eb: EBClient) -> None:
    route = respx.get(f"{BASE}/accounts/u-1/balances").mock(
        return_value=httpx.Response(200, json={"balances": []})
    )
    psu = PsuHeaders(ip_address="10.0.0.5", user_agent="Mozilla/5.0")
    headers = build_psu_headers(psu, ["psu-ip-address", "Psu-User-Agent"])
    await eb.get_balances("u-1", psu_headers=headers)
    sent = route.calls.last.request.headers
    assert sent["Psu-Ip-Address"] == "10.0.0.5"
    assert sent["Psu-User-Agent"] == "Mozilla/5.0"


# --- PSU / redirect (bez sieci) ------------------------------------------------


def test_psu_all_or_none() -> None:
    assert build_psu_headers(None, ["Psu-Ip-Address"]) == {}
    with pytest.raises(PsuHeadersIncomplete, match="Psu-User-Agent"):
        build_psu_headers(PsuHeaders(ip_address="1.2.3.4"), ["Psu-Ip-Address", "Psu-User-Agent"])
    assert PsuHeaders(accept_language="pl").as_headers() == {"Psu-Accept-Language": "pl"}


@pytest.mark.parametrize(
    ("text", "code", "state"),
    [
        ("https://ha/cb?code=abc-123&state=s1", "abc-123", "s1"),
        ("  http://localhost:8099/callback?state=s1&code=xyz  ", "xyz", "s1"),
        ("code=abc&state=s1", "abc", "s1"),
        ("abc-123", "abc-123", None),
    ],
)
def test_parse_redirect(text: str, code: str, state: str | None) -> None:
    result = parse_redirect(text, expected_state="s1")
    assert (result.code, result.state) == (code, state)


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("https://ha/cb?error=access_denied&error_description=User+cancelled", "access_denied"),
        ("https://ha/cb?code=abc&state=other", "state"),
        ("https://ha/cb?state=s1", "code"),
        ("   ", "pusty"),
    ],
)
def test_parse_redirect_errors(text: str, match: str) -> None:
    with pytest.raises(EBAuthError, match=match):
        parse_redirect(text, expected_state="s1")
