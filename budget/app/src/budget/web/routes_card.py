"""Ekran „Karta” (M15 E2): osoby z kartą kredytową i ręczne przypisanie płatności kartą."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget import card
from budget.spending import add_months, month_label, parse_month
from budget.web.common import Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn

    def page(request: Request, month: str | None, error: str = "") -> HTMLResponse:
        today = panel.service.now().date()
        start = parse_month(month, today)
        rows = card.payments(conn, start)
        nxt = add_months(start, 1)
        return panel.render(
            request,
            "card.html",
            cm=card.month_status(conn, start),
            holders=card.holders(conn),
            todo=[t for t in rows if t["card_holder_id"] is None],
            done=[t for t in rows if t["card_holder_id"] is not None],
            ym=f"{start:%Y-%m}",
            label=month_label(start),
            prev=f"{add_months(start, -1):%Y-%m}",
            next=f"{nxt:%Y-%m}" if nxt <= today else None,
            threshold=card.THRESHOLD,
            error=error,
        )

    @r.get("/card", response_class=HTMLResponse)
    async def card_page(request: Request, month: str | None = None) -> HTMLResponse:
        return page(request, month)

    @r.post("/card/assign", response_class=HTMLResponse)
    async def assign(
        request: Request, txn_id: int = Form(...), holder_id: int = Form(...), month: str = Form("")
    ) -> HTMLResponse:
        try:
            card.assign(conn, txn_id, holder_id)
        except card.CardError as exc:  # komunikat w podmienianym #card-main (htmx)
            return page(request, month or None, str(exc))
        return page(request, month or None)

    @r.post("/card/holders")
    async def add_holder(request: Request, name: str = Form("")) -> Response:
        try:
            card.add_holder(conn, name)
        except card.CardError as exc:
            return panel.redirect(request, "/card", str(exc), "error")
        return panel.redirect(request, "/card", "Dodano osobę.")

    @r.post("/card/holders/{holder_id}")
    async def rename_holder(request: Request, holder_id: int, name: str = Form("")) -> Response:
        try:
            card.rename_holder(conn, holder_id, name)
        except card.CardError as exc:
            return panel.redirect(request, "/card", str(exc), "error")
        return panel.redirect(request, "/card", "Zapisano.")

    return r
