"""Ekran „Majątek” (M26 E3): bilans aktywów i pasywów, trend z migawek, płynność i LTV."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from budget import networth, stocks
from budget.web import charts
from budget.web.common import Panel

ASSET_GROUPS = (
    networth.ACCOUNTS,
    networth.SAVINGS,
    networth.PIGGIES,
    networth.INVESTMENTS,
)
LIABILITY_GROUPS = (networth.LOANS, networth.CARD)


def groups(
    nw: networth.NetWorth, order: tuple[str, ...]
) -> list[tuple[str, Decimal, list[networth.Component]]]:
    """Grupy w kolejności `order` jako (nazwa, suma, składniki); puste pomijane."""
    out = []
    for g in order:
        items = [c for c in nw.components if c.group == g]
        if items:
            out.append((g, sum((c.amount for c in items), Decimal(0)), items))
    return out


def router(panel: Panel) -> APIRouter:
    r = APIRouter()

    @r.get("/networth", response_class=HTMLResponse)
    async def networth_page(request: Request) -> HTMLResponse:
        conn = panel.conn
        today = panel.service.now().date()
        adv = panel.service.invest_advice()
        spend = adv.inputs.spend if adv and adv.inputs.spend > 0 else None
        nw = networth.compute(conn, today, spend)
        hist = [p for p in networth.history(conn) if p.day < today.replace(day=1)]
        points = [*hist, networth.Point(today, nw.total, False)]
        return panel.render(
            request,
            "networth.html",
            nw=nw,
            assets=groups(nw, ASSET_GROUPS),
            liabilities=groups(nw, LIABILITY_GROUPS),
            mom=networth.change(conn, nw.total, today, 30),
            yoy=networth.change(conn, nw.total, today, 365),
            chart=charts.networth_line([(p.day, p.total, p.approx) for p in points])
            if len(points) > 1
            else None,
            points=points,
            no_stocks_before=stocks.HISTORY_FROM
            if points[0].day < stocks.HISTORY_FROM and stocks.load(conn)
            else None,
            stale_days=networth.STALE_DAYS,
        )

    return r
