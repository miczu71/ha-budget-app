"""Ekran „Kredyt” (M9 E1): kredyt hipoteczny wpisany ręcznie i jego harmonogram."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget import loan, loan_sim, money, savings
from budget.loan import Scenario
from budget.recurring import series as S
from budget.web.common import Panel

ZERO = money.ZERO


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn

    @r.get("/loan", response_class=HTMLResponse)
    async def loan_page(request: Request, edit: int | None = None) -> HTMLResponse:
        loans = loan.all_loans(conn)
        today = panel.service.now().date()
        schedules = {lo.id: loan.schedule(lo) for lo in loans}
        return panel.render(
            request,
            "loan.html",
            today=today,
            rows=[
                (lo, loan.summary(lo, schedules[lo.id], today), schedules[lo.id]) for lo in loans
            ],
            series=[s for s in S.all_series(conn, ("active",)) if s.direction == "out"],
            account=next(iter(savings.all_accounts(conn)), None),
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
                installment=field.get("installment"),
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

    @r.post("/loan/{loan_id}/series")
    async def link_series(request: Request, loan_id: int, series_id: str = Form("")) -> Response:
        try:
            loan.set_series(conn, loan_id, int(series_id) if series_id.isdigit() else None)
        except (loan.LoanError, S.SeriesError) as exc:
            return panel.redirect(request, "/loan", str(exc), "error")
        return panel.redirect(request, "/loan", "Zapisano powiązanie z serią rat.")

    @r.get("/loan/{loan_id}/calc", response_class=HTMLResponse)
    async def calc(request: Request, loan_id: int) -> HTMLResponse:
        """Wynik kalkulatora scenariuszy (htmx): parametry z formularza w query string."""
        q = request.query_params

        def amount(name: str) -> Decimal | None:
            return money.parse(q.get(name))

        try:
            lo = loan.get(conn, loan_id)
            today = panel.service.now().date()
            principal = loan.summary(lo, loan.schedule(lo), today).principal
            variant = q.get("variant", "shorten")
            if variant not in ("shorten", "lower"):
                raise loan.LoanError("Wybierz wariant: skrócenie okresu albo niższa rata.")
            since = date.fromisoformat(q["since"]) if q.get("since") else None
            scen = Scenario(
                lump=min(max(amount("lump") or ZERO, ZERO), principal),
                monthly=max(amount("monthly") or ZERO, ZERO),
                variant=variant,
                wibor_delta=amount("wibor_delta") or ZERO,
                wibor_from=since,
                margin=amount("margin"),
                margin_from=since,
            )
            accounts = savings.all_accounts(conn)
            acc = loan_sim.account_for(
                accounts[0] if accounts else None,
                amount("savings_rate"),
                q.get("always_promo") == "1",
            )
            months = int(q["months"]) if q.get("months") else None
            sim = loan_sim.simulate(lo, scen, today, acc, months)
            table = loan_sim.variants(lo, scen, today) if sim else []
        except (loan.LoanError, money.AmountError, ValueError) as exc:
            return panel.partial(
                request, "_loan_calc.html", error=str(exc) or "Nieprawidłowe dane."
            )
        return panel.partial(
            request, "_loan_calc.html", error=None, sim=sim, table=table, scen=scen, months=months
        )

    @r.post("/loan/{loan_id}/archive")
    async def archive(request: Request, loan_id: int) -> Response:
        try:
            loan.archive(conn, loan_id)
        except loan.LoanError as exc:
            return panel.redirect(request, "/loan", str(exc), "error")
        return panel.redirect(request, "/loan", "Zarchiwizowano kredyt.")

    return r
