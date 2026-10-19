"""Ekran „Inwestycje” (M22 E1): koszyki, rekomendacja, porównanie opcji, aktywa i oferty."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from budget import invest, invest_blogs, invest_sources, piggy
from budget.spending import month_start
from budget.web.common import Panel

DEFAULT_YEARS = 5
FALLBACK_AMOUNT = Decimal(
    10_000
)  # porównanie bez nadwyżki: kwota przykładowa, do zmiany w formularzu


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn

    def compare_args(
        amount: str | None, years: str | None, surplus: Decimal | None
    ) -> tuple[Decimal, Decimal]:
        """Kwota i horyzont porównania z adresu; domyślnie roczna nadwyżka i 5 lat."""
        try:
            chosen = piggy.parse_amount(amount, "kwotę")
        except piggy.PiggyError:
            chosen = None
        default = surplus * 12 if surplus and surplus > 0 else FALLBACK_AMOUNT
        try:
            horizon = Decimal(int(years or DEFAULT_YEARS))
        except ValueError:
            horizon = Decimal(DEFAULT_YEARS)
        return chosen or default, min(max(horizon, Decimal(1)), Decimal(10))

    @r.get("/invest", response_class=HTMLResponse)
    async def invest_page(
        request: Request,
        amount: str | None = None,
        years: str | None = None,
        edit_asset: int | None = None,
    ) -> HTMLResponse:
        today: date = panel.service.now().date()
        buffer = Decimal(panel.service.settings.forecast_buffer)
        snap = panel.service.snapshot
        proj = panel.service.year_memo.get(snap, today, buffer)
        fc = panel.service.forecast()
        if fc is not None and fc.piggies_from is not None:
            rows = fc.piggies
        else:
            rows = piggy.statuses(snap, today, month_start(today))
        s = invest.load_settings(conn)
        inp = invest.build_inputs(conn, proj, rows, today)
        sum_, horizon = compare_args(amount, years, inp.surplus)
        opts = invest.options(conn, sum_, horizon, today, s)
        assets = invest.all_assets(conn)
        offers = invest.all_offers(conn)
        banks = invest.all_banks(conn)
        clients = [b.name for b in banks]
        return panel.render(
            request,
            "invest.html",
            today=today,
            s=s,
            inp=inp,
            buckets=invest.buckets(inp, s),
            rec=invest.recommend(inp, s, opts),
            options=opts,
            amount=sum_,
            years=int(horizon),
            assets=assets,
            edit_asset=next((a for a in assets if a.id == edit_asset), None),
            offers=offers,
            banks=banks,
            hidden={o.id for o in offers if invest.is_hidden(o, clients)},
            sources_checked=invest_sources.checked(conn),
            sources_error=invest_sources.error(conn),
            blogs_error=invest_blogs.error(conn),
            asset_kinds=invest.ASSET_KINDS,
            offer_kinds=invest.OFFER_KINDS,
        )

    @r.post("/invest/settings")
    async def save_settings(request: Request) -> Response:
        f = {k: str(v) for k, v in (await request.form()).items()}
        try:
            invest.save_settings(
                conn,
                f.get("cushion_months", ""),
                f.get("etf_returns", ""),
                f.get("etf_ter", ""),
                f.get("inflation", ""),
            )
        except invest.InvestError as exc:
            return panel.redirect(request, "/invest#settings", str(exc), "error")
        return panel.redirect(request, "/invest", "Zapisano ustawienia agenta.")

    async def save_asset(request: Request, asset_id: int | None) -> Response:
        f = {k: str(v) for k, v in (await request.form()).items()}
        try:
            invest.save_asset(
                conn,
                asset_id,
                f.get("kind", ""),
                f.get("name", ""),
                f.get("amount"),
                f.get("rate"),
                f.get("start_date"),
                f.get("maturity_date"),
                bool(f.get("ike")),
            )
        except invest.InvestError as exc:
            back = f"/invest?edit_asset={asset_id}#assets" if asset_id else "/invest#assets"
            return panel.redirect(request, back, str(exc), "error")
        return panel.redirect(request, "/invest#assets", "Zapisano aktywo.")

    @r.post("/invest/assets")
    async def add_asset(request: Request) -> Response:
        return await save_asset(request, None)

    @r.post("/invest/assets/{asset_id}")
    async def change_asset(request: Request, asset_id: int) -> Response:
        return await save_asset(request, asset_id)

    @r.post("/invest/assets/{asset_id}/archive")
    async def archive_asset(request: Request, asset_id: int) -> Response:
        invest.archive_asset(conn, asset_id)
        return panel.redirect(request, "/invest#assets", "Zarchiwizowano aktywo.")

    @r.post("/invest/offers")
    async def add_offer(request: Request) -> Response:
        f = {k: str(v) for k, v in (await request.form()).items()}
        try:
            invest.save_offer(
                conn,
                f.get("kind", ""),
                f.get("bank", ""),
                f.get("rate"),
                f.get("margin"),
                f.get("limit_amount"),
                f.get("months"),
                f.get("conditions", ""),
                bool(f.get("new_only")),
            )
        except invest.InvestError as exc:
            return panel.redirect(request, "/invest#offers", str(exc), "error")
        return panel.redirect(request, "/invest#offers", "Dodano ofertę.")

    @r.post("/invest/offers/{offer_id}/confirm")
    async def confirm_offer(request: Request, offer_id: int) -> Response:
        f = {k: str(v) for k, v in (await request.form()).items()}
        fields = (
            {k: f.get(k, "") for k in ("rate", "limit_amount", "months", "conditions")}
            if "rate" in f
            else None
        )
        try:
            invest.confirm_offer(conn, offer_id, f.get("bank", ""), fields)
        except invest.InvestError as exc:
            return panel.redirect(request, "/invest#offers", str(exc), "error")
        return panel.redirect(request, "/invest#offers", "Potwierdzono ofertę.")

    @r.post("/invest/banks")
    async def add_bank(request: Request) -> Response:
        f = await request.form()
        try:
            invest.save_bank(conn, str(f.get("name", "")))
        except invest.InvestError as exc:
            return panel.redirect(request, "/invest#banks", str(exc), "error")
        return panel.redirect(request, "/invest#banks", "Dodano bank.")

    @r.post("/invest/banks/{bank_id}/delete")
    async def delete_bank(request: Request, bank_id: int) -> Response:
        invest.delete_bank(conn, bank_id)
        return panel.redirect(request, "/invest#banks", "Usunięto bank.")

    @r.post("/invest/offers/{offer_id}/archive")
    async def archive_offer(request: Request, offer_id: int) -> Response:
        invest.archive_offer(conn, offer_id)
        return panel.redirect(request, "/invest#offers", "Usunięto ofertę.")

    return r
