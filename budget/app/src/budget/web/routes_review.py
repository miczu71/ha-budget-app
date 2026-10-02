"""Ekran „Do przejrzenia”: nieskategoryzowane w grupach, decyzja dla całej grupy naraz.

Domyślnie zapis tworzy regułę „sprzedawca równa się X” + kierunek (przyszłe transakcje też
dostaną kategorię). Kategoria ręczna („tylko te”) — gdy użytkownik tak wybierze, gdy odznaczy
część pozycji albo dla grup kraju i grup bez nazwy, z których reguły „sprzedawca równa się”
zrobić się nie da.

Widok miesiąca (`month=RRRR-MM`, link z „Wydatków”) zawęża listę i zaznaczanie do pozycji
z miesiąca; reguła zapisana z takiego widoku nadal obejmuje sprzedawcę we wszystkich miesiącach
(podgląd mówi, ile pozycji spoza miesiąca dostanie kategorię).
"""

from __future__ import annotations

from datetime import date
from typing import Any, cast
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from starlette.datastructures import FormData

from budget import ledger, review, spending
from budget.categorize import engine, rules, taxonomy
from budget.categorize.rules import Conditions, Rule, RuleError, TextCondition
from budget.categorize.taxonomy import TaxonomyError
from budget.review import Direction, Group, GroupKey, GroupKind, Sort
from budget.spending import add_months, month_label, parse_month
from budget.suggest import engine as suggest
from budget.web.common import Panel

PAGE = 50


def group_key(kind: Any, value: Any, direction: Any, currency: Any) -> GroupKey | None:
    if kind not in ("merchant", "country") or direction not in review.DIRECTIONS:
        return None
    return GroupKey(
        cast(GroupKind, kind), str(value or ""), cast(Direction, direction), str(currency or "")
    )


def key_from_form(form: FormData) -> GroupKey | None:
    return group_key(
        form.get("kind"), form.get("value"), form.get("direction"), form.get("currency")
    )


def month_of(value: Any, today: date) -> date | None:
    """Miesiąc widoku z parametru `month`; brak → cała kolejka."""
    return parse_month(str(value), today) if value else None


def selected_ids(form: FormData) -> set[int]:
    out = set()
    for v in form.getlist("txn"):
        try:
            out.add(int(str(v)))
        except ValueError:
            continue
    return out


def as_rule(g: Group, selected: set[int], only: bool) -> bool:
    """Reguła tylko dla nazwanego sprzedawcy, bez „tylko te” i z zaznaczoną całą grupą."""
    return g.can_rule and not only and selected == {i.id for i in g.items}


def make_rule(g: Group, category_id: int) -> Rule:
    return Rule(
        None,
        category_id,
        Conditions(
            text=(TextCondition("merchant", "equals", g.key.value),),
            direction=g.key.direction,
        ),
    )


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn

    def today() -> date:
        return panel.service.now().date()

    def coverage(month: date | None) -> spending.Coverage:
        if month is None:
            return spending.coverage(conn)
        return spending.coverage(conn, month, add_months(month, 1))

    def queued(month: date | None) -> int:
        return (
            review.pending_count(conn) if month is None else review.queue(conn, month=month).pending
        )

    def category(form: FormData) -> int | None:
        try:
            cid = int(str(form.get("category_id") or ""))
        except ValueError:
            return None
        return cid if cid in taxonomy.leaves(conn) else None

    def preview_ctx(
        g: Group, selected: set[int], only: bool, cid: int | None, m: date | None
    ) -> dict[str, Any]:
        """Kontekst `_review_preview.html` (podgląd reguły albo kategorii ręcznej)."""
        ctx: dict[str, Any] = {
            "g": g,
            "selected": len(selected),
            "rule": as_rule(g, selected, only),
            "category": taxonomy.all_categories(conn).get(cid) if cid else None,
        }
        if cid is not None and ctx["rule"]:
            p = engine.preview(conn, make_rule(g, cid))
            whole = review.group(conn, g.key) if m else g  # grupa we wszystkich miesiącach
            in_queue = whole.count if whole else g.count
            ctx["p"] = p
            ctx["other_months"] = in_queue - g.count
            ctx["others"] = max(p.changes - in_queue, 0)
        return ctx

    def group_body(
        request: Request, g: Group, gid: str, month: date | None, **extra: Any
    ) -> HTMLResponse:
        return panel.partial(
            request,
            "_review_group.html",
            g=g,
            gid=gid,
            month=month,
            tree=taxonomy.tree(conn),
            **extra,
        )

    @r.get("/review", response_class=HTMLResponse)
    async def review_page(
        request: Request,
        direction: str = "out",
        sort: str = "amount",
        limit: int = PAGE,
        month: str = "",
    ) -> HTMLResponse:
        d: Direction = direction if direction in review.DIRECTIONS else "out"
        s: Sort = sort if sort in review.SORTS else "amount"
        limit = max(PAGE, min(limit, 1000))
        now = today()
        m = month_of(month, now)
        nxt = add_months(m, 1) if m else None
        return panel.render(
            request,
            "review.html",
            q=review.queue(conn, d, s, limit, m),
            ai_on=panel.service.settings.ai_enabled,
            direction=d,
            sort=s,
            limit=limit,
            cov=coverage(m),
            month=m,
            label=month_label(m) if m else "",
            prev_month=add_months(m, -1) if m else None,
            next_month=nxt if nxt and nxt <= now else None,
        )

    @r.get("/review/group", response_class=HTMLResponse)
    async def group(
        request: Request,
        gid: str,
        kind: str = "",
        value: str = "",
        direction: str = "",
        currency: str = "",
        month: str = "",
    ) -> HTMLResponse:
        key = group_key(kind, value, direction, currency)
        m = month_of(month, today())
        g = review.group(conn, key, m) if key else None
        if g is None:
            return HTMLResponse('<p class="muted">Ta grupa jest już przejrzana — odśwież.</p>')
        return group_body(request, g, gid, m)

    @r.post("/review/preview", response_class=HTMLResponse)
    async def preview(request: Request) -> HTMLResponse:
        form = await request.form()
        key = key_from_form(form)
        m = month_of(form.get("month"), today())
        g = review.group(conn, key, m) if key else None
        if g is None:
            return HTMLResponse('<p class="muted">Ta grupa jest już przejrzana — odśwież.</p>')
        selected = selected_ids(form) & {i.id for i in g.items}
        ctx = preview_ctx(g, selected, form.get("only") is not None, category(form), m)
        return panel.partial(request, "_review_preview.html", **ctx)

    @r.get("/review/item", response_class=HTMLResponse)
    async def item(
        request: Request,
        gid: str,
        kind: str = "",
        value: str = "",
        direction: str = "",
        currency: str = "",
        month: str = "",
        pick: int = 0,
    ) -> HTMLResponse:
        """Grupa rozwinięta z kategorią wybraną z podpowiedzi AI i gotowym podglądem."""
        key = group_key(kind, value, direction, currency)
        m = month_of(month, today())
        g = review.group(conn, key, m) if key else None
        if g is None:
            return HTMLResponse('<li class="rv-done muted">Ta grupa jest już przejrzana.</li>')
        cid = pick if pick in taxonomy.leaves(conn) else None
        ctx = preview_ctx(g, {i.id for i in g.items}, False, cid, m)
        return panel.partial(
            request,
            "_review_li.html",
            **ctx,
            gid=gid,
            open=True,
            error=None,
            month=m,
            pick=cid,
            pv=cid is not None,
            tree=taxonomy.tree(conn),
        )

    @r.post("/review/ai-run")
    async def ai_run(request: Request) -> Response:
        form = await request.form()
        back = "/review?" + urlencode(
            {k: str(form.get(k)) for k in ("direction", "sort", "month") if form.get(k)}
        )
        service = panel.service
        if not service.settings.ai_enabled:
            return panel.redirect(request, back, "Podpowiedzi AI są wyłączone.", "warn")
        if service.ai_lock.locked():
            return panel.redirect(request, back, "Podpowiedzi AI już się liczą.", "warn")
        res = await service.suggest()
        text = f"Podpowiedzi AI: zapisanych {res.stored}, bez podpowiedzi zostało {res.waiting}"
        if res.error:
            return panel.redirect(request, back, f"{text} — {res.error}", "error")
        return panel.redirect(request, back, text, "ok" if res.calls else "warn")

    @r.post("/review/assign", response_class=HTMLResponse)
    async def assign(request: Request) -> HTMLResponse:
        form = await request.form()
        gid = str(form.get("gid") or "g")
        key = key_from_form(form)
        m = month_of(form.get("month"), today())
        g = review.group(conn, key, m) if key else None
        if g is None:
            return HTMLResponse('<li class="rv-done muted">Ta grupa jest już przejrzana.</li>')
        selected = selected_ids(form)
        cid = category(form)

        def fail(message: str) -> HTMLResponse:
            return panel.partial(
                request,
                "_review_li.html",
                g=g,
                gid=gid,
                open=True,
                error=message,
                month=m,
                tree=taxonomy.tree(conn),
            )

        if cid is None:
            return fail("Wybierz podkategorię.")
        if not selected:
            return fail("Zaznacz co najmniej jedną transakcję.")
        if not selected <= {i.id for i in g.items}:
            return fail("Lista transakcji się zmieniła — odśwież stronę.")
        use_rule = as_rule(g, selected, form.get("only") is not None)
        try:
            with ledger.transaction(conn):
                if use_rule:
                    rules.save(conn, make_rule(g, cid))
                else:
                    for txn_id in sorted(selected):
                        engine.set_manual(conn, txn_id, cid)
                for merchant in sorted({i.merchant for i in g.items if i.id in selected}):
                    suggest.decide(conn, merchant, g.key.direction, cid)
                changed = engine.recategorize(conn)
        except (RuleError, TaxonomyError) as exc:
            return fail(str(exc))
        name = taxonomy.all_categories(conn)[cid].name
        rest = review.group(conn, g.key, m)
        return panel.partial(
            request,
            "_review_saved.html",
            g=g,
            rest=rest,
            gid=gid,
            rule=use_rule,
            category=name,
            count=len(selected),
            changed=changed,
            pending=review.pending_count(conn),
            queued=queued(m),
            cov=coverage(m),
            month=m,
            tree=taxonomy.tree(conn),
        )

    return r
