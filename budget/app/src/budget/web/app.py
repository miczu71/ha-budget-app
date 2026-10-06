"""Panel add-onu (Ingress) — fabryka aplikacji; ekrany w `routes_*.py`.

- Ingress: prefiks z nagłówka `X-Ingress-Path` trafia do szablonów jako `base`; żądania spoza
  proxy Supervisora (172.30.32.2) są odrzucane (poza trybem dev). Wyjątek: `/calendar.ics`
  także z HA Core (sieć hosta → brama sieci hassio 172.30.32.1) dla Remote Calendar.
- Mobile WebView (aplikacja HA) agresywnie cache'uje: HTML i odpowiedzi `no-store`, statyki
  z `?v=<wersja>` i `immutable`, wersja widoczna w nawigacji. `hx-boost` podmienia tylko treść,
  więc strona otwarta przed aktualizacją zostałaby ze starym CSS — żądanie GET htmx ze starszą
  wersją (`X-Panel-Version`, brak = sprzed 0.23.0) dostaje `HX-Refresh` — pełne przeładowanie.
- Wszystkie endpointy są `async` — działają w pętli usługi (jedno połączenie SQLite).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from budget import __version__
from budget.service import Service
from budget.web import (
    routes_accounts,
    routes_ask,
    routes_bank,
    routes_budget,
    routes_calendar,
    routes_card,
    routes_home,
    routes_import,
    routes_inbox,
    routes_recurring,
    routes_review,
    routes_rules,
    routes_spending,
    routes_status,
    routes_transactions,
)
from budget.web.common import HERE, Panel, fmt_date, fmt_money

__all__ = ["create_app", "fmt_date", "fmt_money"]

log = logging.getLogger(__name__)

INGRESS_PROXY = "172.30.32.2"
HA_CORE = "172.30.32.1"
CALENDAR_PATH = "/calendar.ics"
PANEL_VERSION = "x-panel-version"


def create_app(service: Service, *, dev: bool = False) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    panel = Panel(service)

    @app.middleware("http")
    async def ingress(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        peer = request.client.host if request.client else ""
        calendar = request.url.path == CALENDAR_PATH and peer == HA_CORE
        if not dev and peer != INGRESS_PROXY and not calendar:
            if request.url.path == CALENDAR_PATH:
                log.warning("Kalendarz: odrzucone żądanie z %s", peer)
            return Response("Dostęp tylko przez panel Home Assistant (Ingress).", 403)
        sent = request.headers.get(PANEL_VERSION)
        if request.method == "GET" and request.headers.get("hx-request") and sent != __version__:
            return Response(headers={"HX-Refresh": "true", "Cache-Control": "no-store"})
        response = await call_next(request)
        if request.method == "POST" and response.status_code < 400:
            panel.service.refresh_soon()  # encje Flex po zapisie kwoty, grupy, kategorii
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-store"
        return response

    for module in (
        routes_home,
        routes_status,
        routes_budget,
        routes_spending,
        routes_recurring,
        routes_inbox,
        routes_review,
        routes_transactions,
        routes_rules,
        routes_accounts,
        routes_import,
        routes_bank,
        routes_calendar,
        routes_card,
        routes_ask,
    ):
        app.include_router(module.router(panel))

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app
