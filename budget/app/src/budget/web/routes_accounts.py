"""Ekran Konta: nazwa wyświetlana, rodzaj, „w budżecie”."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget import report
from budget.web.common import ACCOUNT_KINDS, Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    service, conn = panel.service, panel.conn

    @r.get("/accounts", response_class=HTMLResponse)
    async def accounts(request: Request) -> HTMLResponse:
        return panel.render(request, "accounts.html", accounts=report.accounts(conn))

    @r.post("/accounts/{account_id}")
    async def save_account(
        request: Request,
        account_id: int,
        display_name: str = Form(""),
        include_in_budget: str | None = Form(None),
        kind: str | None = Form(None),
    ) -> Response:
        name = display_name.strip()[:60] or None
        if kind is not None and kind not in ACCOUNT_KINDS:
            return panel.redirect(request, "/accounts", "Nieznany rodzaj konta.", "error")
        cur = conn.execute(
            "UPDATE account SET display_name = ?, include_in_budget = ? WHERE id = ?",
            (name, int(include_in_budget is not None), account_id),
        )
        if not cur.rowcount:
            return panel.redirect(request, "/accounts", "Nie ma takiego konta.", "error")
        if kind is not None:  # M32: rodzaj kont z API (np. oszczędnościowe) ustawia się ręcznie
            conn.execute("UPDATE account SET kind = ? WHERE id = ?", (kind, account_id))
        await service.refresh()
        return panel.redirect(request, "/accounts", "Zapisano.")

    return r
