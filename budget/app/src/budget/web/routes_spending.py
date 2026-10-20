"""Ekran Wydatki: miesiąc kalendarzowy w kategoriach (dane: `budget.spending`)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from budget import flow, spending
from budget.spending import month_label, parse_month
from budget.web import charts
from budget.web.common import Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()

    @r.get("/spending", response_class=HTMLResponse)
    async def spending_page(request: Request, month: str | None = None) -> HTMLResponse:
        today = panel.service.now().date()
        start = parse_month(month, today)
        m = spending.build(panel.conn, start, today)
        nxt = spending.add_months(start, 1)
        end = nxt.toordinal() - 1
        period = f"date_from={start.isoformat()}&date_to={date.fromordinal(end).isoformat()}"
        ym = start.strftime("%Y-%m")
        sankey = charts.sankey(
            flow.build(panel.conn, start, nxt),
            period=period,
            other_href=f"/spending?month={ym}",
            review_href=f"/review?month={ym}",
        )
        return panel.render(
            request,
            "spending.html",
            m=m,
            label=month_label(start),
            prev_label=month_label(m.prev_month),
            next_label=month_label(m.next_month) if m.next_month else "",
            sankey=sankey,
            date_from=start.isoformat(),
            date_to=date.fromordinal(end).isoformat(),
        )

    return r
