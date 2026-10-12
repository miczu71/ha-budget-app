"""Zakładki u góry (M28): edytor kolejności i ukrywania."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from budget import nav_layout
from budget.web.common import Panel

LAY = {
    "url": "/tabs",
    "title": "Zakładki",
    "intro": "Przestaw zakładki strzałkami albo ukryj te, których nie potrzebujesz.",
    "done": "/",
}


def router(panel: Panel) -> APIRouter:
    r = APIRouter()

    def edited(request: Request) -> Response:
        if request.headers.get("hx-request"):
            return panel.partial(
                request,
                "_home_layout.html",
                layout=nav_layout.layout.load(panel.conn),
                lay=LAY,
            )
        return panel.redirect(request, "/tabs")

    @r.get("/tabs", response_class=HTMLResponse)
    async def tabs_page(request: Request) -> HTMLResponse:
        return panel.render(
            request, "tabs.html", layout=nav_layout.layout.load(panel.conn), lay=LAY
        )

    @r.post("/tabs/move")
    async def tabs_move(request: Request, key: str = Form(...), delta: int = Form(...)) -> Response:
        if key not in nav_layout.TABS or delta not in (-1, 1):
            raise HTTPException(400)
        nav_layout.layout.move(panel.conn, key, delta)
        return edited(request)

    @r.post("/tabs/toggle")
    async def tabs_toggle(request: Request, key: str = Form(...)) -> Response:
        if key not in nav_layout.TABS:
            raise HTTPException(400)
        nav_layout.layout.toggle(panel.conn, key)
        return edited(request)

    @r.post("/tabs/reset")
    async def tabs_reset(request: Request) -> Response:
        nav_layout.layout.reset(panel.conn)
        return edited(request)

    return r
