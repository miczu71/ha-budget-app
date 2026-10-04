"""Ekran Budżet (M5a): „ile mogę jeszcze wydać” — dane: `budget.flex`."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget import flex
from budget.categorize import taxonomy
from budget.categorize.taxonomy import TaxonomyError
from budget.spending import add_months, month_label, parse_month
from budget.web.common import Panel, fmt_money


def router(panel: Panel) -> APIRouter:
    r = APIRouter()

    @r.get("/budget", response_class=HTMLResponse)
    async def budget_page(
        request: Request, month: str | None = None, fixed: bool = False
    ) -> HTMLResponse:
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
            fixed_open=fixed,
            groups=taxonomy.FLEX_LABELS,
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

    @r.post("/budget/auto")
    async def set_auto(request: Request, month: str = Form("")) -> Response:
        today = panel.service.now().date()
        start = parse_month(month, today)
        flex.set_budget(panel.conn, start, None)
        message = f"Pula automatyczna (z wpływów) — od miesiąca: {month_label(start)}."
        return panel.redirect(request, f"/budget?month={start:%Y-%m}", message)

    @r.post("/budget/fixed")
    async def add_fixed(
        request: Request, category: int = Form(0), month: str = Form("")
    ) -> Response:
        """„Dodaj do stałych” — podkategoria wybrana z listy."""
        return await set_fixed(request, category, month, "fixed")

    @r.post("/budget/fixed/{category_id}")
    async def set_fixed(
        request: Request, category_id: int, month: str = Form(""), flex_group: str = Form("")
    ) -> Response:
        """Grupa podkategorii z rozwinięcia kosztów stałych (jak w Kategoriach)."""
        today = panel.service.now().date()
        start = parse_month(month, today)
        back = f"/budget?month={start:%Y-%m}&fixed=1#fixed"
        try:
            cat = taxonomy.set_flex_group(panel.conn, category_id, flex_group)
        except TaxonomyError as exc:
            return panel.redirect(request, back, str(exc), "error")
        message = f"„{cat.name}” — grupa budżetu: {taxonomy.FLEX_LABELS[flex_group]}."
        auto = flex.auto_budget(panel.conn, start)
        if auto is not None:
            message += f" Pula automatyczna: {fmt_money(auto.amount, 'PLN')}."
        return panel.redirect(request, back, message)

    return r
