"""Ekran „Rok w liczbach” (M25 E3): sumy roku, r/r, zmiany kategorii, sprzedawcy, rekordy."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from budget import recap
from budget.spending import month_label
from budget.web import charts
from budget.web.common import Panel


def default_year(years: list[int], today: date) -> int:
    """Rok bieżący; w styczniu poprzedni (jeśli są z niego dane)."""
    if today.month == 1 and today.year - 1 in years:
        return today.year - 1
    return today.year


def router(panel: Panel) -> APIRouter:
    r = APIRouter()

    @r.get("/recap", response_class=HTMLResponse)
    async def recap_page(request: Request, year: str | None = None) -> HTMLResponse:
        today = panel.service.now().date()
        years = recap.years(panel.conn, today)
        chosen = int(year) if year and year.isdigit() and int(year) in years else None
        rec = recap.build(panel.conn, chosen or default_year(years, today), today)
        return panel.render(
            request,
            "recap.html",
            r=rec,
            years=years,
            last_day=rec.end - timedelta(days=1),
            prev_last=rec.prev.end - timedelta(days=1) if rec.prev else None,
            chart=charts.month_bars(rec.months, date.min),
            label=month_label,
        )

    return r
