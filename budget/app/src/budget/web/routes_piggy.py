"""Ekran „Skarbonki” (M10 E1): skarbonki na kontach-celach i ręczne przypisanie wydatków."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget import piggy, savings
from budget.recurring import series as S
from budget.spending import month_start
from budget.web.common import Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn

    @r.get("/piggy", response_class=HTMLResponse)
    async def piggy_page(
        request: Request, edit: int | None = None, edit_savings: int | None = None
    ) -> HTMLResponse:
        today = panel.service.now().date()
        accts = savings.all_accounts(conn)
        fc = panel.service.forecast()  # ten sam okres i stan co w prognozie „Do wypłaty”
        if fc is not None and fc.piggies_from is not None:
            start, rows = fc.piggies_from, fc.piggies
        else:  # bez sald nie ma prognozy — okres = miesiąc
            start = month_start(today)
            rows = piggy.statuses(panel.service.snapshot, today, start)
        return panel.render(
            request,
            "piggy.html",
            rows=rows,
            today=today,
            period_start=start,
            to_transfer=piggy.total_to_transfer(rows),
            archived=piggy.all_piggies(conn, archived=True),
            series=[s for s in S.all_series(conn, ("active",)) if s.direction == "out"],
            edit=next((s.piggy for s in rows if s.piggy.id == edit), None),
            accounts=[(a, savings.estimate(conn, a, today)) for a in accts],
            edit_savings=next((a for a in accts if a.id == edit_savings), None),
        )

    async def save(request: Request, piggy_id: int | None) -> Response:
        form = await request.form()
        field = {k: str(v) for k, v in form.items()}
        series = field.get("series_id", "")
        try:
            piggy.save(
                conn,
                piggy_id=piggy_id,
                name=field.get("name", ""),
                account_number=field.get("account_number", ""),
                target=field.get("target"),
                due_date=field.get("due_date"),
                series_id=int(series) if series.isdigit() else None,
                opening_balance=field.get("opening_balance"),
            )
        except (piggy.PiggyError, S.SeriesError) as exc:
            back = f"/piggy?edit={piggy_id}" if piggy_id else "/piggy"
            return panel.redirect(request, back, str(exc), "error")
        return panel.redirect(request, "/piggy", "Zapisano skarbonkę.")

    @r.post("/piggy")
    async def add(request: Request) -> Response:
        return await save(request, None)

    @r.post("/piggy/{piggy_id}")
    async def change(request: Request, piggy_id: int) -> Response:
        return await save(request, piggy_id)

    @r.post("/piggy/{piggy_id}/archive")
    async def archive(request: Request, piggy_id: int, restore: str = Form("")) -> Response:
        try:
            piggy.archive(conn, piggy_id, archived=not restore)
        except piggy.PiggyError as exc:
            return panel.redirect(request, "/piggy", str(exc), "error")
        return panel.redirect(request, "/piggy", "Przywrócono." if restore else "Zarchiwizowano.")

    async def save_savings(request: Request, account_id: int | None) -> Response:
        field = {k: str(v) for k, v in (await request.form()).items()}
        try:
            savings.save(
                conn,
                account_id=account_id,
                name=field.get("name", ""),
                account_number=field.get("account_number", ""),
                opening_balance=field.get("opening_balance"),
                opening_date=field.get("opening_date"),
                base_rate=field.get("base_rate"),
                promo_rate=field.get("promo_rate"),
                promo_limit=field.get("promo_limit"),
                promo_until=field.get("promo_until"),
            )
        except piggy.PiggyError as exc:
            back = f"/piggy?edit_savings={account_id}" if account_id else "/piggy"
            return panel.redirect(request, back, str(exc), "error")
        return panel.redirect(request, "/piggy", "Zapisano konto oszczędnościowe.")

    @r.post("/savings")
    async def add_savings(request: Request) -> Response:
        return await save_savings(request, None)

    @r.post("/savings/{account_id}")
    async def change_savings(request: Request, account_id: int) -> Response:
        return await save_savings(request, account_id)

    @r.post("/savings/{account_id}/archive")
    async def archive_savings(request: Request, account_id: int) -> Response:
        try:
            savings.archive(conn, account_id)
        except piggy.PiggyError as exc:
            return panel.redirect(request, "/piggy", str(exc), "error")
        return panel.redirect(request, "/piggy", "Zarchiwizowano konto.")

    @r.post("/transactions/{txn_id}/piggy", response_class=HTMLResponse)
    async def assign(request: Request, txn_id: int, piggy_id: str = Form("")) -> HTMLResponse:
        error = ""
        try:
            piggy.assign(conn, txn_id, int(piggy_id) if piggy_id.isdigit() else None)
        except piggy.PiggyError as exc:
            error = str(exc)
        t = conn.execute("SELECT id, piggy_id FROM txn WHERE id = ?", (txn_id,)).fetchone()
        return panel.render(
            request, "_txn_piggy.html", t=t, piggies=piggy.all_piggies(conn), error=error
        )

    return r
