"""Panel add-onu (Ingress) — fabryka aplikacji; ekrany w `routes_*.py`.

- Ingress: prefiks z nagłówka `X-Ingress-Path` trafia do szablonów jako `base`; żądania spoza
  proxy Supervisora (172.30.32.2) są odrzucane (poza trybem dev).
- Mobile WebView (aplikacja HA) agresywnie cache'uje: HTML i odpowiedzi `no-store`, statyki
  z `?v=<wersja>` i `immutable`, wersja widoczna w nawigacji.
- Wszystkie endpointy są `async` — działają w pętli usługi (jedno połączenie SQLite).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from budget import __version__
from budget.service import Service
from budget.web import (
    routes_accounts,
    routes_bank,
    routes_budget,
    routes_home,
    routes_import,
    routes_inbox,
    routes_recurring,
    routes_review,
    routes_rules,
    routes_spending,
    routes_status,
    routes_theme,
    routes_transactions,
)
from budget.web.common import HERE, Panel, fmt_date, fmt_money

__all__ = ["create_app", "fmt_date", "fmt_money"]

INGRESS_PROXY = "172.30.32.2"


def create_app(service: Service, *, dev: bool = False) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    panel = Panel(service)

    @app.middleware("http")
    async def ingress(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        peer = request.client.host if request.client else ""
        if not dev and peer != INGRESS_PROXY:
            return Response("Dostęp tylko przez panel Home Assistant (Ingress).", 403)
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
        routes_theme,
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
    ):
        app.include_router(module.router(panel))

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app
