"""Ekran Cykliczne (M5b E1): propozycje serii do potwierdzenia, lista i edycja serii.

Przynależność transakcji liczona przy każdym wyświetleniu (`recurring.series.assign`), więc
zmiana warunków serii od razu zmienia listę jej transakcji. Warunki edytowane tymi samymi
polami co reguły kategorii (`web.rule_form`, `_rule_conditions.html`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget.categorize.rules import Rule, RuleError
from budget.recurring import series as S
from budget.recurring.series import Candidate, Series, SeriesError
from budget.web.common import Panel
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


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn
    panel.templates.env.globals["cadences"] = S.CADENCES
    panel.templates.env.globals["series_statuses"] = S.STATUSES

    def views() -> list[View]:
        all_series = S.all_series(conn)
        members = S.assign(all_series, S.candidates(conn))
        names = accounts(conn)
        return [View(s, members.get(s.id, []), describe(_as_rule(s), names)) for s in all_series]

    @r.get("/recurring", response_class=HTMLResponse)
    async def recurring_page(request: Request) -> HTMLResponse:
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
        )

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

    return r
