"""Ekran „Kredyt” (M9 E1): kredyt hipoteczny wpisany ręcznie i jego harmonogram."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from budget import loan
from budget.web.common import Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn

    @r.get("/loan", response_class=HTMLResponse)
    async def loan_page(request: Request, edit: int | None = None) -> HTMLResponse:
        loans = loan.all_loans(conn)
        schedules = {lo.id: loan.schedule(lo) for lo in loans}
        return panel.render(
            request,
            "loan.html",
            today=panel.service.now().date(),
            rows=[(lo, loan.summary(schedules[lo.id]), schedules[lo.id]) for lo in loans],
            edit=next((lo for lo in loans if lo.id == edit), None),
            kinds=loan.KINDS,
        )

    async def save(request: Request, loan_id: int | None) -> Response:
        field = {k: str(v) for k, v in (await request.form()).items()}
        try:
            loan.save(
                conn,
                loan_id=loan_id,
                name=field.get("name", ""),
                principal=field.get("principal"),
                principal_date=field.get("principal_date"),
                reference_rate=field.get("reference_rate"),
                margin=field.get("margin"),
                installment_kind=field.get("installment_kind", ""),
                last_payment_date=field.get("last_payment_date"),
                payment_day=field.get("payment_day"),
            )
        except loan.LoanError as exc:
            back = f"/loan?edit={loan_id}" if loan_id else "/loan"
            return panel.redirect(request, back, str(exc), "error")
        return panel.redirect(request, "/loan", "Zapisano kredyt.")

    @r.post("/loan")
    async def add(request: Request) -> Response:
        return await save(request, None)

    @r.post("/loan/{loan_id}")
    async def change(request: Request, loan_id: int) -> Response:
        return await save(request, loan_id)

    @r.post("/loan/{loan_id}/archive")
    async def archive(request: Request, loan_id: int) -> Response:
        try:
            loan.archive(conn, loan_id)
        except loan.LoanError as exc:
            return panel.redirect(request, "/loan", str(exc), "error")
        return panel.redirect(request, "/loan", "Zarchiwizowano kredyt.")

    return r
