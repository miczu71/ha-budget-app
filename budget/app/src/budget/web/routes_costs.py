"""Ekran „Koszty banku” (M23 E4): przewalutowanie względem NBP i opłaty banku w roku."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from budget import hidden_costs
from budget.spending import MONTHS, add_months, month_start
from budget.web.common import Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn

    @r.get("/costs", response_class=HTMLResponse)
    async def costs_page(request: Request, year: int | None = None) -> HTMLResponse:
        today = panel.service.now().date()
        y = year if year and 2000 <= year <= today.year else today.year
        start, end = date(y, 1, 1), date(y + 1, 1, 1)
        months = hidden_costs.months(conn, start, min(end, add_months(month_start(today), 1)))
        top = max((m.total for m in months), default=Decimal("0"))
        return panel.render(
            request,
            "costs.html",
            year=y,
            c=hidden_costs.build(conn, start, end),
            months=[(MONTHS[m.start.month - 1], m) for m in reversed(months)],
            top=top,
            csv_until=hidden_costs.csv_until(conn),
            prev=y - 1,
            next=y + 1 if y < today.year else None,
        )

    return r
