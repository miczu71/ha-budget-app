"""Ekran Budżet (M5a): „ile mogę jeszcze wydać” — dane: `budget.flex`."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget import flex
from budget.spending import add_months, month_label, parse_month
from budget.web.common import Panel, fmt_money


def router(panel: Panel) -> APIRouter:
    r = APIRouter()

    @r.get("/budget", response_class=HTMLResponse)
    async def budget_page(request: Request, month: str | None = None) -> HTMLResponse:
        today = panel.service.now().date()
        start = parse_month(month, today)
        f = flex.build(panel.conn, start, today)
        end = add_months(start, 1).toordinal() - 1
        return panel.render(
            request,
            "budget.html",
            f=f,
            label=month_label(start),
            prev_label=month_label(f.prev_month),
            next_label=month_label(f.next_month) if f.next_month else "",
            date_from=start.isoformat(),
            date_to=date.fromordinal(end).isoformat(),
        )

    @r.post("/budget/amount")
    async def set_amount(
        request: Request, month: str = Form(""), amount: str = Form("")
    ) -> Response:
        today = panel.service.now().date()
        start = parse_month(month, today)
        back = f"/budget?month={start:%Y-%m}"
        try:
            value = flex.parse_amount(amount)
        except flex.FlexError as exc:
            return panel.redirect(request, back, str(exc), "error")
        flex.set_budget(panel.conn, start, value)
        amount_text = fmt_money(value, "PLN")
        message = f"Budżet elastyczny {amount_text} — od miesiąca: {month_label(start)}."
        return panel.redirect(request, back, message)

    return r
