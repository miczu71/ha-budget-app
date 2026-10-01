"""Asynchroniczny klient Enable Banking API (AIS, tylko odczyt) — SPEC §2.2–2.3."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Self
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pydantic import BaseModel, ConfigDict

from budget.eb_models import (
    Application,
    Aspsp,
    AuthResponse,
    Balance,
    SessionInfo,
    SessionResponse,
    Transaction,
    TransactionsPage,
)

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.enablebanking.com"
DEFAULT_TOKEN_TTL = 3600
MAX_TOKEN_TTL = 86400
_TOKEN_REFRESH_MARGIN = 60
DEFAULT_CONSENT_DAYS = 90


class EBError(Exception):
    def __init__(self, status: int, code: str | None, message: str) -> None:
        super().__init__(f"Enable Banking {status} {code or ''}: {message}".strip())
        self.status = status
        self.code = code
        self.message = message


class EBRateLimited(EBError):
    """429 / limit banku — przejść do następnego slotu (SPEC §5.1)."""


class EBSessionExpired(EBError):
    """Zgoda wygasła lub odwołana — potrzebny ponowny redirect + SCA."""


class EBAuthError(Exception):
    """Błąd zwrócony w redirect URL (`?error=…`) albo niezgodny `state`."""


class PsuHeadersIncomplete(ValueError):
    """Wysłanie tylko części wymaganych nagłówków PSU kończy się `PSU_HEADER_NOT_PROVIDED`."""


class PsuHeaders(BaseModel):
    """Dane obecnego użytkownika — zapytanie z nimi nie liczy się do limitu 4/dobę."""

    model_config = ConfigDict(frozen=True)

    ip_address: str | None = None
    user_agent: str | None = None
    referer: str | None = None
    accept: str | None = None
    accept_charset: str | None = None
    accept_encoding: str | None = None
    accept_language: str | None = None
    geo_location: str | None = None

    def as_headers(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for field, value in self.model_dump(exclude_none=True).items():
            name = "Psu-" + "-".join(part.capitalize() for part in field.split("_"))
            out[name] = value
        return out


def build_psu_headers(psu: PsuHeaders | None, required: Sequence[str]) -> dict[str, str]:
    """Wszystkie wymagane nagłówki albo żaden (SPEC §2.3)."""
    if psu is None:
        return {}
    headers = psu.as_headers()
    present = {name.lower() for name in headers}
    missing = [name for name in required if name.lower() not in present]
    if missing:
        raise PsuHeadersIncomplete(f"brak wymaganych nagłówków PSU: {', '.join(missing)}")
    return headers


@dataclass(frozen=True)
class RedirectResult:
    code: str
    state: str | None


def parse_redirect(text: str, expected_state: str | None = None) -> RedirectResult:
    """Wyciąga `code` z wklejonego adresu zwrotnego albo przyjmuje sam kod."""
    text = text.strip()
    if not text:
        raise EBAuthError("pusty adres zwrotny")
    if "?" in text or "code=" in text or "error=" in text:
        query = parse_qs(urlparse(text).query if "?" in text else text)
        if "error" in query:
            desc = query.get("error_description", [""])[0]
            raise EBAuthError(f"bank odrzucił autoryzację: {query['error'][0]} {desc}".strip())
        if "code" not in query:
            raise EBAuthError("w adresie nie ma parametru code")
        code = query["code"][0]
        state = query.get("state", [None])[0]
        # Sam kod (bez state) przyjmujemy — nie da się go zweryfikować, ale SPEC §7 na to pozwala
        if expected_state is not None and state is not None and state != expected_state:
            raise EBAuthError("parametr state nie zgadza się z rozpoczętą autoryzacją")
        return RedirectResult(code=code, state=state)
    return RedirectResult(code=text, state=None)


def load_private_key(pem: bytes) -> RSAPrivateKey:
    key = load_pem_private_key(pem, password=None)
    if not isinstance(key, RSAPrivateKey):
        raise ValueError("klucz Enable Banking musi być kluczem RSA (RS256)")
    return key


class EBClient:
    def __init__(
        self,
        app_id: str,
        private_key_pem: bytes,
        *,
        base_url: str = DEFAULT_BASE_URL,
        http: httpx.AsyncClient | None = None,
        token_ttl: int = DEFAULT_TOKEN_TTL,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not 0 < token_ttl <= MAX_TOKEN_TTL:
            raise ValueError(f"token_ttl musi być w zakresie 1..{MAX_TOKEN_TTL}")
        self._app_id = app_id
        self._key = load_private_key(private_key_pem)
        self._base_url = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        self._owns_http = http is None
        self._ttl = token_ttl
        self._clock = clock
        self._token: str | None = None
        self._token_exp = 0.0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    # --- JWT ---------------------------------------------------------------

    def token(self, *, force: bool = False) -> str:
        now = self._clock()
        if force or self._token is None or now >= self._token_exp - _TOKEN_REFRESH_MARGIN:
            iat = int(now)
            body = {
                "iss": "enablebanking.com",
                "aud": "api.enablebanking.com",
                "iat": iat,
                "exp": iat + self._ttl,
            }
            self._token = jwt.encode(
                body, self._key, algorithm="RS256", headers={"kid": self._app_id, "typ": "JWT"}
            )
            self._token_exp = iat + self._ttl
        return self._token

    # --- HTTP --------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        url = self._base_url + path
        response: httpx.Response | None = None
        for attempt in range(2):
            req_headers = {"Authorization": f"Bearer {self.token(force=attempt > 0)}"}
            req_headers.update(headers or {})
            response = await self._http.request(
                method, url, params=params, json=json, headers=req_headers
            )
            if response.status_code != 401:
                break
            log.warning("Enable Banking 401 na %s %s — odnawiam JWT", method, path)
        assert response is not None
        if response.is_success:
            return response.json() if response.content else None
        raise _to_error(response)

    # --- API ---------------------------------------------------------------

    async def get_application(self) -> Application:
        return Application.model_validate(await self._request("GET", "/application"))

    async def get_aspsps(
        self, country: str | None = None, psu_type: str = "personal", service: str = "AIS"
    ) -> list[Aspsp]:
        params = {"psu_type": psu_type, "service": service}
        if country:
            params["country"] = country
        data = await self._request("GET", "/aspsps", params=params)
        return [Aspsp.model_validate(a) for a in data.get("aspsps", [])]

    async def start_auth(
        self,
        aspsp: Aspsp,
        redirect_url: str,
        *,
        state: str | None = None,
        psu_type: str = "personal",
        valid_until: datetime | None = None,
        language: str | None = None,
    ) -> tuple[AuthResponse, str, datetime]:
        """`POST /auth` → (odpowiedź z `url`, `state` do weryfikacji, `valid_until`)."""
        state = state or str(uuid.uuid4())
        if valid_until is None:
            seconds = aspsp.maximum_consent_validity or DEFAULT_CONSENT_DAYS * 86400
            # Zapas na opóźnienie między POST /auth a SCA — bank odrzuca valid_until > maksimum
            seconds = max(seconds - 3600, 3600)
            now = datetime.fromtimestamp(self._clock(), UTC)
            valid_until = now + timedelta(seconds=seconds)
        body: dict[str, Any] = {
            "access": {
                "valid_until": valid_until.astimezone(UTC).isoformat(timespec="seconds"),
                "balances": True,
                "transactions": True,
            },
            "aspsp": {"name": aspsp.name, "country": aspsp.country},
            "state": state,
            "redirect_url": redirect_url,
            "psu_type": psu_type,
        }
        if language:
            body["language"] = language
        data = await self._request("POST", "/auth", json=body)
        return AuthResponse.model_validate(data), state, valid_until

    async def create_session(self, code: str) -> SessionResponse:
        data = await self._request("POST", "/sessions", json={"code": code})
        return SessionResponse.from_api(data)

    async def get_session(self, session_id: str) -> SessionInfo:
        return SessionInfo.from_api(await self._request("GET", f"/sessions/{session_id}"))

    async def delete_session(self, session_id: str) -> None:
        await self._request("DELETE", f"/sessions/{session_id}")

    async def get_balances(
        self, account_uid: str, *, psu_headers: Mapping[str, str] | None = None
    ) -> list[Balance]:
        data = await self._request("GET", f"/accounts/{account_uid}/balances", headers=psu_headers)
        return [Balance.from_api(b) for b in data.get("balances", [])]

    async def iter_transaction_pages(
        self,
        account_uid: str,
        date_from: date,
        date_to: date | None = None,
        *,
        transaction_status: str | None = None,
        psu_headers: Mapping[str, str] | None = None,
    ) -> AsyncIterator[TransactionsPage]:
        params = {"date_from": date_from.isoformat()}
        if date_to:
            params["date_to"] = date_to.isoformat()
        if transaction_status:
            params["transaction_status"] = transaction_status
        seen_keys: set[str] = set()
        while True:
            data = await self._request(
                "GET", f"/accounts/{account_uid}/transactions", params=params, headers=psu_headers
            )
            page = TransactionsPage.from_api(data)
            yield page
            key = page.continuation_key
            if not key:
                return
            if key in seen_keys:
                raise EBError(200, "PAGINATION_LOOP", "powtórzony continuation_key")
            seen_keys.add(key)
            params["continuation_key"] = key

    async def iter_transactions(
        self,
        account_uid: str,
        date_from: date,
        date_to: date | None = None,
        *,
        transaction_status: str | None = None,
        psu_headers: Mapping[str, str] | None = None,
    ) -> AsyncIterator[Transaction]:
        async for page in self.iter_transaction_pages(
            account_uid,
            date_from,
            date_to,
            transaction_status=transaction_status,
            psu_headers=psu_headers,
        ):
            for txn in page.transactions:
                yield txn


def find_aspsp(aspsps: Sequence[Aspsp], name: str, country: str | None = None) -> Aspsp:
    """Dokładne dopasowanie nazwy, a gdy go nie ma — jedyne dopasowanie po fragmencie."""
    pool = [a for a in aspsps if country is None or a.country == country.upper()]
    exact = [a for a in pool if a.name.casefold() == name.casefold()]
    if len(exact) == 1:
        return exact[0]
    partial = [a for a in pool if name.casefold() in a.name.casefold()]
    if len(partial) == 1:
        return partial[0]
    found = ", ".join(sorted(a.name for a in partial)) or "brak"
    raise LookupError(f"bank '{name}' nie jest jednoznaczny (pasujące: {found})")


_SESSION_ERROR_CODES = {"EXPIRED_SESSION", "REVOKED_SESSION", "CLOSED_SESSION"}


def _to_error(response: httpx.Response) -> EBError:
    code: str | None = None
    message = response.text[:500]
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        code = body.get("code") or body.get("error")
        message = str(body.get("message") or body.get("detail") or message)
    status = response.status_code
    if status == 429 or code == "ASPSP_RATE_LIMIT_EXCEEDED":
        return EBRateLimited(status, code, message)
    if code in _SESSION_ERROR_CODES:
        return EBSessionExpired(status, code, message)
    return EBError(status, code, message)
