"""Kalendarz płatności (M6): `/calendar.ics` dla integracji HA Remote Calendar.

Jedyna trasa dostępna spoza proxy Ingress — z HA Core (allowlista w `app.py`)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from budget import calendar_ics
from budget.web.common import Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    service = panel.service

    @r.get("/calendar.ics")
    async def calendar() -> Response:
        now = service.now()
        body = calendar_ics.build(service.snapshot, now.date(), now)
        return Response(body, media_type="text/calendar; charset=utf-8")

    return r
