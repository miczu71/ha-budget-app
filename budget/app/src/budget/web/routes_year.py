"""Ekran „Rok” (M18 E1): prognoza salda miesiąc po miesiącu, cel i „ile mogę wydać”."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget import year
from budget.spending import month_label
from budget.web import charts
from budget.web.common import Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn

    @r.get("/year", response_class=HTMLResponse)
    async def year_page(request: Request) -> HTMLResponse:
        today = panel.service.now().date()
        buffer = Decimal(panel.service.settings.forecast_buffer)
        snap = panel.service.snapshot
        proj = panel.service.year_memo.get(snap, today, buffer)
        chart = charts.forecast_line(proj.balance_points(today), buffer) if proj else None
        return panel.render(
            request,
            "year.html",
            p=proj,
            chart=chart,
            today=today,
            end=year.horizon_end(today),
            label=month_label,
            unseried=year.unseried(snap, today) if proj else [],
            manual_flex=year.settings(conn)[0],
            buffer=buffer,
        )

    @r.post("/year/settings")
    async def save_settings(
        request: Request, flex: str = Form(""), target: str = Form("")
    ) -> Response:
        try:
            year.save_settings(conn, flex, target)
        except year.YearError as exc:
            return panel.redirect(request, "/year", str(exc), "error")
        return panel.redirect(request, "/year", "Zapisano ustawienia prognozy rocznej.", "ok")

    return r
