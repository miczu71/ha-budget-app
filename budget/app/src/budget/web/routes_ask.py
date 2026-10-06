"""Zakładka „Zapytaj”: czat z danymi (M12, dane i LLM: `budget.ask`)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from budget.ask import engine
from budget.web.common import Panel

EXAMPLES = (
    "Ile wydaliśmy na jedzenie w tym roku?",
    "Który miesiąc w ostatnim roku był najdroższy?",
    "Na co wydajemy najwięcej w ostatnich 12 miesiącach?",
    "Ile średnio miesięcznie kosztują nas koszty stałe?",
    "Restauracje: ten rok vs zeszły rok",
)
RECENT = 5


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn

    def left() -> int:
        return engine.questions_left(conn, panel.service.settings, panel.service.now().date())

    def page(request: Request, **ctx: object) -> HTMLResponse:
        recent = list(dict.fromkeys(e["q"] for e in engine.history(conn)))[:RECENT]
        return panel.render(
            request,
            "ask.html",
            ai_on=engine.enabled(panel.service.settings),
            left=left(),
            examples=EXAMPLES,
            recent=recent,
            question_max=engine.QUESTION_MAX,
            **ctx,
        )

    @r.get("/ask", response_class=HTMLResponse)
    async def ask_page(request: Request) -> HTMLResponse:
        return page(request)

    @r.post("/ask", response_class=HTMLResponse)
    async def ask(request: Request) -> HTMLResponse:
        form = await request.form()
        question = str(form.get("example") or form.get("q") or "")  # przykład ma pierwszeństwo
        s = panel.service.settings
        a = (
            await engine.ask(conn, s, question, panel.service.now().date())
            if engine.enabled(s)
            else None
        )
        if request.headers.get("hx-request"):  # formularz ma własny hx-post (bez hx-boost)
            return panel.partial(request, "_ask_answer.html", a=a, left=left())
        return page(request, a=a, q=question)

    return r
