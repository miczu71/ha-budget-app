"""Strona główna (M13): podsumowanie budżetu — dane z `budget.flex` i centrum powiadomień."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from budget import flex
from budget.spending import month_label, parse_month
from budget.web.common import Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()

    @r.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        today = panel.service.now().date()
        start = parse_month(None, today)
        return panel.render(
            request,
            "home.html",
            f=flex.build(panel.conn, start, today),
            label=month_label(start),
            month=start.strftime("%Y-%m"),
        )

    return r
