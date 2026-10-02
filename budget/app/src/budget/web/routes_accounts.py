"""Ekran Konta: nazwa wyświetlana, „w budżecie”."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget import report
from budget.web.common import Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    service, conn = panel.service, panel.conn

    @r.get("/accounts", response_class=HTMLResponse)
    async def accounts(request: Request) -> HTMLResponse:
        return panel.render(request, "accounts.html", rep=report.build(conn))

    @r.post("/accounts/{account_id}")
    async def save_account(
        request: Request,
        account_id: int,
        display_name: str = Form(""),
        include_in_budget: str | None = Form(None),
    ) -> Response:
        name = display_name.strip()[:60] or None
        cur = conn.execute(
            "UPDATE account SET display_name = ?, include_in_budget = ? WHERE id = ?",
            (name, int(include_in_budget is not None), account_id),
        )
        if not cur.rowcount:
            return panel.redirect(request, "/accounts", "Nie ma takiego konta.", "error")
        await service.refresh()
        return panel.redirect(request, "/accounts", "Zapisano.")

    return r
