"""Centrum powiadomień (dzwonek, M5b) — karty z `budget.inbox`."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from budget.web.common import Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()

    @r.get("/inbox", response_class=HTMLResponse)
    async def inbox_page(request: Request) -> HTMLResponse:
        return panel.render(request, "inbox.html", items=panel.service.inbox())

    return r
