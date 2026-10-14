"""Ekran „Rok” (M18 E1): prognoza salda miesiąc po miesiącu, cel i „ile mogę wydać”."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget import year, year_events
from budget.recurring import series as S
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
        chart = None
        if proj:
            second = proj.scenario.balance_points(today) if proj.scenario else ()
            chart = charts.forecast_line(proj.balance_points(today), buffer, second=second)
        live = S.all_series(conn, ("active",))
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
            events=year_events.active(conn),
            proposals=year_events.proposals(snap, today) if proj else [],
            series=live,
            series_names={s.id: s.name for s in live},
            kinds=year_events.KINDS,
            modes=year_events.MODES,
            this_month=today.strftime("%Y-%m"),
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

    async def save_event(request: Request, event_id: int | None) -> Response:
        form = {k: str(v) for k, v in (await request.form()).items()}
        try:
            year_events.save_form(conn, event_id, form)
        except year_events.YearEventError as exc:
            return panel.redirect(request, "/year#year-events", str(exc), "error")
        done = "Dodano zdarzenie." if event_id is None else "Zapisano zdarzenie."
        return panel.redirect(request, "/year#year-events", done, "ok")

    @r.post("/year/events")
    async def add_event(request: Request) -> Response:
        return await save_event(request, None)

    @r.post("/year/events/{event_id}")
    async def edit_event(request: Request, event_id: int) -> Response:
        return await save_event(request, event_id)

    @r.post("/year/events/{event_id}/delete")
    async def delete_event(request: Request, event_id: int) -> Response:
        try:
            year_events.delete(conn, event_id)
        except year_events.YearEventError as exc:
            return panel.redirect(request, "/year#year-events", str(exc), "error")
        return panel.redirect(request, "/year#year-events", "Usunięto zdarzenie.", "ok")

    @r.post("/year/proposals")
    async def decide_proposal(
        request: Request, key: str = Form(""), action: str = Form("")
    ) -> Response:
        today = panel.service.now().date()
        found = next(
            (p for p in year_events.proposals(panel.service.snapshot, today) if p.key == key), None
        )
        if found is None or action not in ("approve", "dismiss"):
            return panel.redirect(
                request, "/year#year-events", "Ta propozycja jest nieaktualna.", "error"
            )
        year_events.decide(conn, found, approve=action == "approve")
        done = "Zatwierdzono propozycję." if action == "approve" else "Odrzucono propozycję."
        return panel.redirect(request, "/year#year-events", done, "ok")

    return r
