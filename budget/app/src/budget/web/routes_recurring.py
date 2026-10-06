"""Ekran Cykliczne (M5b E1): propozycje serii do potwierdzenia, lista i edycja serii.

Przynależność transakcji liczona przy każdym wyświetleniu (`recurring.series.assign`), więc
zmiana warunków serii od razu zmienia listę jej transakcji. Warunki edytowane tymi samymi
polami co reguły kategorii (`web.rule_form`, `_rule_conditions.html`).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response
from starlette.datastructures import FormData

from budget import forecast, money
from budget.categorize.rules import Conditions, Rule, RuleError, TextCondition
from budget.ledger import transaction
from budget.recurring import changes, schedule
from budget.recurring import series as S
from budget.recurring.series import Candidate, Series, SeriesError
from budget.spending import add_months, month_label, parse_month
from budget.storage import db
from budget.web.common import Panel
from budget.web.routes_transactions import txn_row
from budget.web.rule_form import (
    accounts,
    check_fragments,
    conditions_context,
    describe,
    rule_from_form,
)

RECENT = 6  # ostatnie transakcje przy propozycji
MEMBERS_MAX = 36  # transakcje na stronie serii


@dataclass
class View:
    s: Series
    members: list[Candidate] = field(default_factory=list)
    conditions: str = ""

    @property
    def last(self) -> Candidate | None:
        return self.members[-1] if self.members else None

    @property
    def recent(self) -> list[Candidate]:
        return list(reversed(self.members[-RECENT:]))

    @property
    def few_history(self) -> bool:
        return S.few_history(self.s, self.members)


def _as_rule(s: Series) -> Rule:
    return Rule(id=None, category_id=0, conditions=s.conditions)


def _draft(t: sqlite3.Row) -> Series:
    """Seria ręczna podpowiedziana z transakcji: sprzedawca równa się + kierunek, co miesiąc."""
    amount = abs(Decimal(t["amount"]))
    direction = "out" if str(t["amount"]).startswith("-") else "in"
    merchant = t["merchant"] or ""
    text = (TextCondition("merchant", "equals", merchant),) if merchant else ()
    return Series(
        id=0,
        name=(merchant or t["counterparty_name"] or "Płatność")[: S.NAME_MAX],
        direction=direction,
        cadence="M",
        conditions=Conditions(text=text, direction=direction),
        expected_amount=amount,
        tolerance=max(amount * Decimal("0.10"), Decimal("5.00")).quantize(money.CENT),
        anchor_day=date.fromisoformat(str(t["day"])[:10]).day,
        status="active",
        origin="manual",
        group_key=None,
        created_at="",
        decided_at=None,
    )


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn
    snap = panel.service.snapshot
    panel.templates.env.globals["cadences"] = S.CADENCES
    panel.templates.env.globals["series_statuses"] = S.STATUSES
    panel.templates.env.globals["due_labels"] = schedule.STATUS_LABELS

    def views() -> list[View]:
        all_series = S.all_series(conn)
        members = S.assign(all_series, snap.candidates())
        names = accounts(conn)
        return [View(s, members.get(s.id, []), describe(_as_rule(s), names)) for s in all_series]

    @r.get("/recurring", response_class=HTMLResponse)
    async def recurring_page(request: Request, month: str | None = None) -> HTMLResponse:
        today = panel.service.now().date()
        start = parse_month(month, today)
        nxt = add_months(start, 1)
        vs = views()
        by_status: dict[str, list[View]] = {k: [] for k in S.STATUSES}
        for v in vs:
            by_status[v.s.status].append(v)
        for k in ("active", "ended"):
            by_status[k].sort(key=lambda v: (v.s.direction, -v.s.monthly, v.s.name))
        return panel.render(
            request,
            "recurring.html",
            proposed=by_status["proposed"],
            active=by_status["active"],
            ended=by_status["ended"],
            rejected=len(by_status["rejected"]),
            mv=schedule.for_month(snap, start, today),
            changes=changes.for_db(snap, today),
            label=month_label(start),
            prev_month=add_months(start, -1),
            prev_label=month_label(add_months(start, -1)),
            next_month=nxt if nxt <= today.replace(day=1) else None,
            next_label=month_label(nxt),
        )

    def form_series(form: FormData) -> tuple[Series, Conditions]:
        """Seria z pól formularza nowej serii po walidacji (`SeriesError`/`RuleError`)."""
        cond = rule_from_form(form).conditions
        check_fragments(cond)
        name, amount, tol = S.validate(
            str(form.get("name") or ""),
            str(form.get("cadence") or ""),
            cond,
            S.parse_amount(str(form.get("expected_amount") or "")),
            S.parse_amount(str(form.get("tolerance") or "")),
        )
        try:
            anchor = int(str(form.get("anchor_day") or ""))
        except ValueError:
            anchor = None
        s = Series(
            id=0,
            name=name,
            direction=str(cond.direction),
            cadence=str(form.get("cadence")),
            conditions=cond,
            expected_amount=amount,
            tolerance=tol,
            anchor_day=anchor,
            status="active",
            origin="manual",
            group_key=None,
            created_at="",
            decided_at=None,
        )
        return s, cond

    @r.get("/recurring/new", response_class=HTMLResponse)
    async def new_series_page(request: Request, txn: int = 0) -> Response:
        t = txn_row(conn, txn)
        if t is None:
            return panel.redirect(request, "/transactions", "Nie ma takiej transakcji.", "error")
        draft = _draft(t)
        return panel.render(
            request,
            "series_new.html",
            draft=draft,
            **conditions_context(conn, _as_rule(draft)),
        )

    @r.post("/recurring/new/preview", response_class=HTMLResponse)
    async def new_series_preview(request: Request) -> HTMLResponse:
        form = await request.form()
        try:
            s, _ = form_series(form)
        except (SeriesError, RuleError) as exc:
            return panel.partial(request, "_series_preview.html", error=str(exc))
        probe = replace(s, id=-1)
        others = S.all_series(conn)
        txns = snap.candidates()
        mine = S.assign([*others, probe], txns)[-1]
        alone = S.assign([probe], txns)[-1]
        return panel.partial(
            request,
            "_series_preview.html",
            describe=describe(_as_rule(probe), accounts(conn)),
            members=mine,
            stolen=len(alone) - len(mine),
        )

    @r.post("/recurring/new")
    async def new_series_save(request: Request) -> Response:
        form = await request.form()
        try:
            s, cond = form_series(form)
        except (SeriesError, RuleError) as exc:
            return panel.redirect(request, "/transactions", str(exc), "error")
        merchant = next((c.value for c in cond.text if c.field == "merchant"), None)
        key = S.group_key(merchant, s.direction) if merchant and len(cond.text) == 1 else None
        with transaction(conn):
            new_id = S.insert(
                conn,
                name=s.name,
                direction=s.direction,
                cadence=s.cadence,
                conditions=cond,
                expected=s.expected_amount,
                tolerance=s.tolerance,
                anchor_day=s.anchor_day,
                status="active",
                origin="manual",
                key=key,
            )
        return panel.redirect(request, f"/recurring/{new_id}", f"Seria „{s.name}” utworzona.")

    @r.get("/recurring/{series_id}", response_class=HTMLResponse)
    async def series_page(request: Request, series_id: int) -> Response:
        v = next((v for v in views() if v.s.id == series_id), None)
        if v is None or v.s.status == "rejected":
            return panel.redirect(request, "/recurring", "Nie ma takiej serii.", "error")
        return panel.render(
            request,
            "series.html",
            v=v,
            members=list(reversed(v.members))[:MEMBERS_MAX],
            is_payday=forecast.payday_series_id(conn) == series_id,
            **conditions_context(conn, _as_rule(v.s)),
        )

    @r.post("/recurring/detect")
    async def detect_now(request: Request) -> Response:
        found = panel.service.detect_series()
        message = (
            f"Nowe propozycje: {len(found)}." if found else "Brak nowych płatności cyklicznych."
        )
        return panel.redirect(request, "/recurring", message)

    @r.post("/recurring/{series_id}/save")
    async def save(request: Request, series_id: int) -> Response:
        form = await request.form()
        back = f"/recurring/{series_id}"
        try:
            cond = rule_from_form(form).conditions
            check_fragments(cond)
            s = S.save(
                conn,
                series_id,
                name=str(form.get("name") or ""),
                cadence=str(form.get("cadence") or ""),
                conditions=cond,
                expected=S.parse_amount(str(form.get("expected_amount") or "")),
                tolerance=S.parse_amount(str(form.get("tolerance") or "")),
                activate=form.get("confirm") is not None,
            )
        except (SeriesError, RuleError) as exc:
            return panel.redirect(request, back, str(exc), "error")
        verb = "potwierdzona" if form.get("confirm") is not None else "zapisana"
        return panel.redirect(request, "/recurring", f"Seria „{s.name}” {verb}.")

    @r.post("/recurring/{series_id}/payday")
    async def set_payday(request: Request, series_id: int, on: str = Form("")) -> Response:
        back = f"/recurring/{series_id}"
        try:
            s = S.get(conn, series_id)
        except SeriesError as exc:
            return panel.redirect(request, "/recurring", str(exc), "error")
        if on == "1":
            if s.direction != "in" or s.status != "active":
                return panel.redirect(
                    request, back, "Wypłatą może być tylko aktywna seria wpływów.", "error"
                )
            db.kv_set(conn, forecast.PAYDAY_KEY, series_id)
            message = f"„{s.name}” to Twoja wypłata — prognoza liczy do jej terminu."
        else:
            if forecast.payday_series_id(conn) == series_id:
                db.kv_set(conn, forecast.PAYDAY_KEY, None)
            message = "Prognoza liczy do wypłaty o największej kwocie."
        return panel.redirect(request, back, message)

    @r.post("/recurring/{series_id}/status")
    async def set_status(request: Request, series_id: int, action: str = Form("")) -> Response:
        if action not in S.TRANSITIONS:
            return panel.redirect(request, "/recurring", "Nieznana akcja.", "error")
        try:
            s = S.set_status(conn, series_id, action)
        except SeriesError as exc:
            return panel.redirect(request, "/recurring", str(exc), "error")
        messages = {
            "confirm": "potwierdzona",
            "reject": "odrzucona — nie będzie proponowana ponownie",
            "end": "zakończona",
            "restore": "przywrócona",
        }
        return panel.redirect(request, "/recurring", f"Seria „{s.name}” {messages[action]}.")

    @r.post("/recurring/{series_id}/change")
    async def decide_change(
        request: Request,
        series_id: int,
        kind: str = Form(""),
        period: str = Form(""),
        action: str = Form(""),
    ) -> Response:
        """Decyzja o zmianie serii z sekcji „Zmiany” (kwotę „przyjmij nową” liczy serwer)."""
        back = "/recurring#changes"
        try:
            if action == "end":
                s = S.set_status(conn, series_id, "end")
                return panel.redirect(request, back, f"Seria „{s.name}” zakończona.")
            if action == "accept":
                today = panel.service.now().date()
                found = next(
                    (
                        c
                        for c in changes.for_db(snap, today)
                        if (c.series.id, c.kind, c.period) == (series_id, kind, period)
                        and c.amount is not None
                    ),
                    None,
                )
                if found is None or found.amount is None:
                    return panel.redirect(request, back, "Ta zmiana już nie istnieje.", "error")
                changes.accept_amount(conn, series_id, found.amount)
                message = f"Nowa kwota serii „{found.series.name}”: {money.fmt(found.amount)}."
                return panel.redirect(request, back, message)
            if changes.DECISIONS.get(kind) == action:
                changes.ack(conn, series_id, period, kind)
                return panel.redirect(request, back, "Zapisano decyzję.")
        except SeriesError as exc:
            return panel.redirect(request, back, str(exc), "error")
        return panel.redirect(request, back, "Nieznana akcja.", "error")

    return r
