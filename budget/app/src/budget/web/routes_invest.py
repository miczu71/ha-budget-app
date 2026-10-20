"""Ekran „Inwestycje” (M22 E1): koszyki, rekomendacja, porównanie opcji, aktywa i oferty."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from budget import invest, invest_blogs, invest_sources, invest_why, piggy, promo_track, savings
from budget.web.common import Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn

    def compare_args(amount: str | None, years: str | None) -> tuple[Decimal | None, Decimal]:
        """Kwota (None = roczna nadwyżka) i horyzont porównania z adresu, domyślnie 5 lat."""
        try:
            chosen = piggy.parse_amount(amount, "kwotę")
        except piggy.PiggyError:
            chosen = None
        try:
            horizon = Decimal(int(years or invest.DEFAULT_YEARS))
        except ValueError:
            horizon = invest.DEFAULT_YEARS
        return chosen, min(max(horizon, Decimal(1)), Decimal(10))

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
        chosen, horizon = compare_args(amount, years)
        adv = panel.service.advice_memo.get(snap, fc, proj, today, chosen, horizon)
        assets = invest.all_assets(conn)
        offers = invest.all_offers(conn)
        promos = promo_track.tracks(conn)
        banks = invest.all_banks(conn)
        clients = [b.name for b in banks]
        return panel.render(
            request,
            "invest.html",
            today=today,
            s=adv.settings,
            inp=adv.inputs,
            buckets=adv.buckets,
            rec=adv.rec,
            why=invest_why.text(conn, adv, snap),
            options=adv.options,
            amount=adv.amount,
            years=int(horizon),
            assets=assets,
            edit_asset=next((a for a in assets if a.id == edit_asset), None),
            offers=offers,
            promos=promos,
            promo_due=promo_track.register(promos),
            tracked={t.offer_id for t in promos if t.status == "active"},
            condition_kinds=promo_track.KIND_LABELS,
            banks=banks,
            hidden={o.id for o in offers if invest.is_hidden(o, clients)},
            sources_checked=invest_sources.checked(conn),
            sources_error=invest_sources.error(conn),
            blogs_error=invest_blogs.error(conn),
            asset_kinds=invest.ASSET_KINDS,
            savings_accounts=savings.all_accounts(conn),
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
                f.get("better_offer", ""),
            )
        except invest.InvestError as exc:
            return panel.redirect(request, "/invest#settings", str(exc), "error")
        return panel.redirect(request, "/invest", "Zapisano ustawienia agenta.")

    async def save_asset(request: Request, asset_id: int | None) -> Response:
        f = {k: str(v) for k, v in (await request.form()).items()}
        try:
            saved = invest.save_asset(
                conn,
                asset_id,
                f.get("kind", ""),
                f.get("name", ""),
                f.get("amount"),
                f.get("rate"),
                f.get("start_date"),
                f.get("maturity_date"),
                bool(f.get("ike")),
                f.get("valued_at"),
            )
            link = f.get("savings_id", "")
            invest.link_savings(conn, saved, int(link) if link.isdigit() else None)
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

    def promo_action(request: Request, done: str, action: Callable[[], object]) -> Response:
        try:
            action()
        except piggy.PiggyError as exc:
            return panel.redirect(request, "/invest#promos", str(exc), "error")
        return panel.redirect(request, "/invest#promos", done)

    @r.post("/invest/offers/{offer_id}/track")
    async def start_track(request: Request, offer_id: int) -> Response:
        today = panel.service.now().date()
        try:
            track_id = promo_track.start(conn, offer_id, today)
        except piggy.PiggyError as exc:
            return panel.redirect(request, "/invest#offers", str(exc), "error")
        note = await promo_track.propose(conn, panel.service.settings, today, track_id)
        if note:
            panel.flash.append(("warn", note))
        return panel.redirect(request, "/invest#promos", "Dodano promocję do śledzenia.")

    @r.post("/invest/promos/{track_id}/bonus")
    async def set_bonus(request: Request, track_id: int) -> Response:
        f = await request.form()
        return promo_action(
            request,
            "Zapisano premię.",
            lambda: promo_track.set_bonus(conn, track_id, str(f.get("bonus", ""))),
        )

    @r.post("/invest/promos/{track_id}/conditions")
    async def add_condition(request: Request, track_id: int) -> Response:
        f = {k: str(v) for k, v in (await request.form()).items()}
        return promo_action(
            request,
            "Dodano warunek.",
            lambda: promo_track.add_condition(
                conn, track_id, f.get("kind", ""), f.get("label", ""), f.get("target")
            ),
        )

    @r.post("/invest/promos/conditions/{condition_id}/toggle")
    async def toggle_condition(request: Request, condition_id: int) -> Response:
        return promo_action(
            request, "Zapisano.", lambda: promo_track.toggle_condition(conn, condition_id)
        )

    @r.post("/invest/promos/conditions/{condition_id}/confirm")
    async def confirm_condition(request: Request, condition_id: int) -> Response:
        return promo_action(
            request,
            "Zatwierdzono warunek.",
            lambda: promo_track.confirm_condition(conn, condition_id),
        )

    @r.post("/invest/promos/conditions/{condition_id}/delete")
    async def delete_condition(request: Request, condition_id: int) -> Response:
        return promo_action(
            request, "Usunięto warunek.", lambda: promo_track.delete_condition(conn, condition_id)
        )

    @r.post("/invest/promos/{track_id}/status")
    async def set_status(request: Request, track_id: int) -> Response:
        f = await request.form()
        return promo_action(
            request,
            "Zapisano.",
            lambda: promo_track.set_status(conn, track_id, str(f.get("status", ""))),
        )

    @r.post("/invest/promos/{track_id}/paid")
    async def mark_paid(request: Request, track_id: int) -> Response:
        f = await request.form()
        today = panel.service.now().date()
        return promo_action(
            request,
            "Zapisano wypłatę premii.",
            lambda: promo_track.mark_paid(conn, track_id, str(f.get("paid_to", "")), today),
        )

    return r
