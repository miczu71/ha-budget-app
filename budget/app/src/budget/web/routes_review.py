"""Ekran „Do przejrzenia”: nieskategoryzowane w grupach, decyzja dla całej grupy naraz.

Domyślnie zapis tworzy regułę „sprzedawca równa się X” + kierunek (przyszłe transakcje też
dostaną kategorię). Tekst reguły można skrócić do fragmentu nazwy i zmienić warunek na „zawiera”
albo „zaczyna się od” (np. cała sieć sklepów jedną regułą) — warunek musi nadal obejmować
sprzedawcę grupy, a podgląd pokazuje, co jeszcze z kolejki złapie.

Kategoria ręczna („tylko te”) — gdy użytkownik tak wybierze, gdy odznaczy część pozycji albo
dla grup kraju i grup bez nazwy, z których reguły „sprzedawca równa się” zrobić się nie da.

Filtr `ai=<id podkategorii>` (przy włączonych podpowiedziach AI) zostawia grupy sprzedawców, które
mają tę podkategorię wśród swoich propozycji (dowolnej z 3); w takim widoku przy każdej grupie jest
„✓ <podkategoria>” — zapis reguły dla całej grupy jednym dotknięciem (wybór kategorii to filtr).

Widok miesiąca (`month=RRRR-MM`, link z „Wydatków”) zawęża listę i zaznaczanie do pozycji
z miesiąca; reguła zapisana z takiego widoku nadal obejmuje sprzedawcę we wszystkich miesiącach
(podgląd mówi, ile pozycji spoza miesiąca dostanie kategorię).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Any, cast
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from starlette.datastructures import FormData

from budget import ledger, review, spending
from budget.categorize import engine, rules, taxonomy
from budget.categorize.rules import Conditions, Rule, RuleError, TextCondition
from budget.categorize.taxonomy import Category, TaxonomyError
from budget.normalize import fold
from budget.review import Direction, Group, GroupKey, GroupKind, Sort
from budget.spending import add_months, month_label, parse_month
from budget.suggest import engine as suggest
from budget.web.common import Panel

PAGE = 50
MIN_FRAGMENT = 3  # znaki (bez ogonków) w tekście reguły „zawiera” / „zaczyna się od”


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


def rule_condition(g: Group, form: FormData | None = None) -> TextCondition:
    """Warunek tekstowy reguły z kolejki: domyślnie „sprzedawca równa się <nazwa grupy>”, z pól
    `rule_op` / `rule_text` — skrócony tekst i inny warunek. `RuleError`, gdy warunek nie obejmie
    sprzedawcy grupy albo fragment jest za krótki."""
    op = str(form.get("rule_op") or "equals") if form else "equals"
    text = re.sub(r"\s+", " ", str(form.get("rule_text") or "")).strip() if form else ""
    text = text or g.key.value
    if op not in rules.OPS:
        raise RuleError("Nieznany warunek reguły.")
    if op != "equals" and len(fold(text)) < MIN_FRAGMENT:
        raise RuleError(f"Tekst reguły musi mieć co najmniej {MIN_FRAGMENT} znaki.")
    cond = TextCondition("merchant", op, text)
    if not cond.matches_text(g.key.value):
        raise RuleError(f"„{text}” nie pasuje do „{g.label}” — reguła nie objęłaby tej grupy.")
    return cond


def make_rule(g: Group, category_id: int, cond: TextCondition | None = None) -> Rule:
    return Rule(
        None,
        category_id,
        Conditions(text=(cond or rule_condition(g),), direction=g.key.direction),
    )


def elsewhere(groups: list[Group], g: Group, cond: TextCondition) -> Counter[str]:
    """Pozycje z innych grup kolejki (wszystkie miesiące), które złapie reguła — po sprzedawcy."""
    out: Counter[str] = Counter()
    for other in groups:
        if other.key == g.key or other.key.direction != g.key.direction:
            continue
        for i in other.items:
            if cond.matches_text(i.merchant):
                out[i.merchant] += 1
    return out


def ai_filters(
    groups: list[Group], direction: Direction, cands: dict[str, list[suggest.Candidate]]
) -> list[tuple[Category, int]]:
    """Podkategorie z propozycji AI dla grup sprzedawców w kierunku: (podkategoria, ile grup),
    od najliczniejszej."""
    count: Counter[int] = Counter()
    cats: dict[int, Category] = {}
    for g in groups:
        if g.key.kind != "merchant" or g.key.direction != direction:
            continue
        for c in cands.get(g.key.value, []):
            count[c.category.id] += 1
            cats[c.category.id] = c.category
    return sorted(((cats[cid], n) for cid, n in count.items()), key=lambda cn: (-cn[1], cn[0].name))


def form_values(form: FormData) -> dict[str, Any]:
    """Pola tekstu reguły do ponownego wyświetlenia formularza po błędzie."""
    return {"rule_op": form.get("rule_op"), "rule_text": form.get("rule_text")}


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
        g: Group,
        selected: set[int],
        only: bool,
        cid: int | None,
        m: date | None,
        form: FormData | None = None,
    ) -> dict[str, Any]:
        """Kontekst `_review_preview.html` (podgląd reguły albo kategorii ręcznej)."""
        ctx: dict[str, Any] = {
            "g": g,
            "selected": len(selected),
            "rule": as_rule(g, selected, only),
            "category": taxonomy.all_categories(conn).get(cid) if cid else None,
        }
        if not ctx["rule"]:
            return ctx
        try:
            cond = ctx["cond"] = rule_condition(g, form)
        except RuleError as exc:
            ctx["rule_error"] = str(exc)
            return ctx
        if cid is not None:
            p = engine.preview(conn, make_rule(g, cid, cond))
            groups = review.all_groups(conn)  # wszystkie miesiące
            whole = next((o for o in groups if o.key == g.key), None) if m else g
            in_queue = whole.count if whole else g.count
            caught = elsewhere(groups, g, cond)
            ctx["p"] = p
            ctx["other_months"] = in_queue - g.count
            ctx["caught"] = caught
            ctx["others"] = max(p.changes - in_queue - caught.total(), 0)
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
        ai: int = 0,
    ) -> HTMLResponse:
        d: Direction = direction if direction in review.DIRECTIONS else "out"
        s: Sort = sort if sort in review.SORTS else "amount"
        limit = max(PAGE, min(limit, 1000))
        now = today()
        m = month_of(month, now)
        nxt = add_months(m, 1) if m else None
        ai_on = panel.service.settings.ai_enabled
        cands = suggest.pending_candidates(conn, d) if ai_on else {}
        ai = ai if ai_on and ai > 0 else 0
        only = {mc for mc, cs in cands.items() if any(c.category.id == ai for c in cs)}
        return panel.render(
            request,
            "review.html",
            q=review.queue(conn, d, s, limit, m, only if ai else None),
            ai_on=ai_on,
            ai=ai,
            ai_filters=ai_filters(review.all_groups(conn, m), d, cands) if cands else [],
            ai_name=getattr(taxonomy.all_categories(conn).get(ai), "name", ""),
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
        ctx = preview_ctx(g, selected, form.get("only") is not None, category(form), m, form)
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
            {k: str(form.get(k)) for k in ("direction", "sort", "month", "ai") if form.get(k)}
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
        # „✓” w filtrze AI — cała grupa bez listy pozycji w formularzu
        selected = {i.id for i in g.items} if form.get("all") else selected_ids(form)
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
                pick=cid,
                tree=taxonomy.tree(conn),
                **form_values(form),
            )

        if cid is None:
            return fail("Wybierz podkategorię.")
        if not selected:
            return fail("Zaznacz co najmniej jedną transakcję.")
        if not selected <= {i.id for i in g.items}:
            return fail("Lista transakcji się zmieniła — odśwież stronę.")
        use_rule = as_rule(g, selected, form.get("only") is not None)
        caught: Counter[str] = Counter()
        try:
            decided = {i.merchant for i in g.items if i.id in selected}
            if use_rule:
                cond = rule_condition(g, form)
                caught = elsewhere(review.all_groups(conn), g, cond)
                decided |= set(caught)
            with ledger.transaction(conn):
                if use_rule:
                    rules.save(conn, make_rule(g, cid, cond))
                else:
                    for txn_id in sorted(selected):
                        engine.set_manual(conn, txn_id, cid)
                for merchant in sorted(decided):
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
            caught=caught,
            changed=changed,
            pending=review.pending_count(conn),
            queued=queued(m),
            cov=coverage(m),
            month=m,
            tree=taxonomy.tree(conn),
        )

    return r
