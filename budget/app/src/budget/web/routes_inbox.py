"""Centrum powiadomień (dzwonek, M5b) — karty z `budget.inbox`."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget import inbox
from budget.web.common import Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()

    @r.get("/inbox", response_class=HTMLResponse)
    async def inbox_page(request: Request) -> HTMLResponse:
        every = inbox.not_deleted(panel.conn, panel.service.inbox_all())
        shown = inbox.visible(panel.conn, every)
        return panel.render(
            request, "inbox.html", items=shown, hidden_count=len(every) - len(shown)
        )

    @r.post("/inbox/dismiss")
    async def inbox_dismiss(
        request: Request, key: str = Form(...), back: str = Form("/inbox")
    ) -> Response:
        inbox.dismiss(panel.conn, key, panel.service.inbox_all())
        panel.service.refresh_soon()
        return panel.redirect(request, back if back in ("/", "/inbox") else "/inbox")

    @r.post("/inbox/delete")
    async def inbox_delete(
        request: Request, key: str = Form(...), back: str = Form("/inbox")
    ) -> Response:
        if not any(i.key == key and i.severity == "error" for i in panel.service.inbox_all()):
            inbox.delete(panel.conn, key)  # karty błędów (zgoda, synchronizacje) tylko się ukrywa
            panel.service.refresh_soon()
        return panel.redirect(request, back if back in ("/", "/inbox") else "/inbox")

    @r.post("/inbox/restore")
    async def inbox_restore(request: Request) -> Response:
        inbox.restore(panel.conn)
        panel.service.refresh_soon()
        return panel.redirect(request, "/inbox")

    return r
