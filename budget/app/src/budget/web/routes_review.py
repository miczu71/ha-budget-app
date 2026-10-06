"""Ekran „Do przejrzenia”: nieskategoryzowane w grupach, decyzja dla całej grupy naraz.

Domyślnie zapis nadaje kategorię ręczną zaznaczonym pozycjom (bez reguły — przyszłe transakcje
sprzedawcy wrócą do kolejki jako nowe pozycje); odznaczone zostają w kolejce. Regułę tworzy się
na żądanie („utwórz regułę”, `make_rule`) w każdej grupie: domyślnie „sprzedawca równa się X”
+ kierunek (X — sprzedawca grupy, w grupie kraju najczęstszy; grupa bez nazwy — warunek do
wpisania). Warunek można zmienić (inne pole, „zawiera” / „zaczyna się od” z fragmentem tekstu),
a pod „więcej warunków” dodać kolejne (wszystkie muszą być spełnione): drugie i trzecie pole
tekstowe, konto, typ, kierunek, kwotę od–do i nazwę sprzedawcy — te same pola co w edytorze
Reguł (`web.rule_form`). W trybie reguły to warunki wybierają pozycje (pola wyboru pozycji są
ignorowane); reguła musi złapać co najmniej jedną pozycję grupy, reszta zostaje w kolejce (tak
rozbija się mieszankę pod jednym odbiorcą). Podgląd pokazuje, ile pozycji grupy złapie, które
zostaną i co jeszcze z kolejki obejmie.

Filtr `ai=<id podkategorii>` (przy włączonych podpowiedziach AI) zostawia grupy sprzedawców, które
mają tę podkategorię wśród swoich propozycji (dowolnej z 3); w takim widoku przy każdej grupie jest
„✓ <podkategoria>” — kategoria ręczna dla całej grupy jednym dotknięciem (wybór kategorii to
filtr).

Sekcja „Przypisane automatycznie” (M7 E2): pozycje z pamięci sprzedawcy w grupach (sprzedawca,
kierunek, waluta, kategoria). ✓ przy grupie i „Potwierdź wszystkie” zapisują tę samą kategorię jako
ręczną (pamięć się umacnia); inna kategoria z rozwiniętej grupy też jest ręczna — decyzje sprzedawcy
przestają być zgodne, więc pamięć dla niego się wyłącza, a reszta jego pozycji wraca do kolejki.

Widok miesiąca (`month=RRRR-MM`, link z „Wydatków”) zawęża listę i zaznaczanie do pozycji
z miesiąca; reguła zapisana z takiego widoku nadal działa we wszystkich miesiącach (podgląd mówi,
ile pozycji spoza miesiąca dostanie kategorię).
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import replace
from datetime import date
from typing import Any, cast
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from starlette.datastructures import FormData

from budget import ledger, review, spending
from budget.categorize import engine, rules, taxonomy
from budget.categorize.rules import Conditions, Facts, Rule, RuleError, TextCondition
from budget.categorize.taxonomy import Category, TaxonomyError
from budget.review import Direction, Group, GroupKey, GroupKind, Item, LearnedKey, Sort
from budget.spending import add_months, month_label, parse_month
from budget.suggest import engine as suggest
from budget.web.common import Panel
from budget.web.rule_form import (
    RULE,
    accounts,
    check_fragments,
    conditions_context,
    describe,
    form_rule,
    requested,
)

PAGE = 50
AI_TOP = 8  # podkategorie filtra AI widoczne od razu; reszta pod „więcej”


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


def learned_key(form: Any) -> LearnedKey | None:
    """Grupa sekcji „przypisane automatycznie” z parametrów (`cat` — kategoria z pamięci)."""
    direction = form.get("direction")
    try:
        cat = int(str(form.get("cat") or ""))
    except ValueError:
        return None
    if direction not in review.DIRECTIONS:
        return None
    return LearnedKey(
        str(form.get("merchant") or ""),
        cast(Direction, direction),
        str(form.get("currency") or ""),
        cat,
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


def default_rule(g: Group) -> Rule:
    """Reguła z kolejki bez zmian użytkownika: „sprzedawca równa się <sprzedawca grupy>”
    + kierunek (grupa bez nazwy — bez warunku tekstowego, trzeba go wpisać)."""
    m = g.default_merchant
    text = (TextCondition("merchant", "equals", m),) if m else ()
    return Rule(None, 0, Conditions(text=text, direction=g.key.direction))


def queue_facts(conn: sqlite3.Connection, groups: list[Group]) -> dict[int, Facts]:
    return engine.facts(conn, [i.id for o in groups for i in o.items])


def caught_ids(items: list[Item], cond: Conditions, facts: dict[int, Facts]) -> set[int]:
    return {i.id for i in items if i.id in facts and cond.matches(facts[i.id])}


def check_rule(
    conn: sqlite3.Connection, g: Group, rule: Rule, facts: dict[int, Facts]
) -> Conditions:
    """Warunki reguły z kolejki po walidacji: `RuleError`, gdy fragment tekstu jest za krótki
    albo reguła nie złapie żadnej pozycji grupy (część grupy wystarczy — reszta zostaje w
    kolejce)."""
    cond = rules.clean_conditions(conn, rule.conditions)
    check_fragments(cond)
    if not caught_ids(g.items, cond, facts):
        raise RuleError(
            f"Warunki nie pasują do żadnej pozycji grupy „{g.label}” — reguła nie objęłaby "
            "tej grupy."
        )
    return cond


def elsewhere(
    groups: list[Group], g: Group, cond: Conditions, facts: dict[int, Facts]
) -> Counter[str]:
    """Pozycje z innych grup kolejki (wszystkie miesiące), które złapie reguła — po sprzedawcy."""
    out: Counter[str] = Counter()
    for other in groups:
        if other.key == g.key:
            continue
        for i in other.items:
            if i.id in facts and cond.matches(facts[i.id]):
                out[i.merchant] += 1
    return out


def closed_merchants(
    groups: list[Group], cond: Conditions, facts: dict[int, Facts]
) -> set[tuple[str, Direction]]:
    """(sprzedawca, kierunek), których reguła obejmie wszystkie pozycje w kolejce — tylko dla
    nich podpowiedź AI jest rozstrzygnięta (częściowe pokrycie zostawia ją resztkom)."""
    hit: dict[tuple[str, Direction], bool] = {}
    for o in groups:
        for i in o.items:
            key = (i.merchant, o.key.direction)
            ok = i.id in facts and cond.matches(facts[i.id])
            hit[key] = hit.get(key, True) and ok
    return {k for k, ok in hit.items() if ok}


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
        cid: int | None,
        m: date | None,
        form: FormData | None = None,
    ) -> dict[str, Any]:
        """Kontekst `_review_preview.html` (podgląd reguły albo kategorii ręcznej)."""
        ctx: dict[str, Any] = {
            "g": g,
            "selected": len(selected),
            "rule": requested(form),
            "category": taxonomy.all_categories(conn).get(cid) if cid else None,
        }
        if not ctx["rule"]:
            return ctx
        groups = review.all_groups(conn)  # wszystkie miesiące
        facts = queue_facts(conn, groups)
        try:
            candidate = form_rule(form, default_rule(g))
            cond = check_rule(conn, g, candidate, facts)
        except RuleError as exc:
            ctx["rule_error"] = str(exc)
            return ctx
        candidate = replace(candidate, conditions=cond)
        here = caught_ids(g.items, cond, facts)
        ctx["describe"] = describe(candidate, accounts(conn))
        ctx["here"] = len(here)
        ctx["left"] = [i for i in g.items if i.id not in here]
        if cid is not None:
            p = engine.preview(conn, replace(candidate, category_id=cid))
            whole = next((o for o in groups if o.key == g.key), g) if m else g
            in_queue = len(caught_ids(whole.items, cond, facts))
            caught = elsewhere(groups, g, cond, facts)
            ctx["p"] = p
            ctx["other_months"] = in_queue - len(here)
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
            **conditions_context(conn, default_rule(g), RULE),
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
            learned=review.learned(conn, d, m),
            ai_on=ai_on,
            ai=ai,
            ai_filters=ai_filters(review.all_groups(conn, m), d, cands) if cands else [],
            ai_top=AI_TOP,
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
        ctx = preview_ctx(g, selected, category(form), m, form)
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
        ctx = preview_ctx(g, {i.id for i in g.items}, cid, m)
        return panel.partial(
            request,
            "_review_li.html",
            **conditions_context(conn, default_rule(g), RULE),
            **ctx,
            gid=gid,
            open=True,
            error=None,
            month=m,
            pick=cid,
            pv=cid is not None,
            tree=taxonomy.tree(conn),
        )

    @r.get("/review/learned/edit", response_class=HTMLResponse)
    async def learned_edit(request: Request, month: str = "") -> HTMLResponse:
        key = learned_key(request.query_params)
        m = month_of(month, today())
        g = review.learned_group(conn, key, m) if key else None
        if g is None:
            return HTMLResponse('<p class="muted">Ta grupa jest już przejrzana — odśwież.</p>')
        return panel.partial(
            request, "_review_learned_edit.html", g=g, month=m, tree=taxonomy.tree(conn)
        )

    @r.post("/review/learned", response_class=HTMLResponse)
    async def learned_save(request: Request) -> HTMLResponse:
        """✓ grupy, „Potwierdź wszystkie” (`all`) albo inna kategoria (`category_id`)."""
        form = await request.form()
        way = form.get("direction")
        d: Direction = way if way in review.DIRECTIONS else "out"
        m = month_of(form.get("month"), today())
        if form.get("all"):
            groups = review.learned(conn, d, m)
        else:
            key = learned_key(form)
            one = review.learned_group(conn, key, m) if key else None
            groups = [one] if one else []
        new = category(form)
        count = 0
        with ledger.transaction(conn):
            for g in groups:
                cid = new or g.key.category_id
                for i in g.items:
                    engine.set_manual(conn, i.id, cid)
                suggest.decide(conn, g.key.merchant, g.key.direction, cid)
                count += len(g.items)
            engine.recategorize(conn)
        if not groups:
            saved = "Nic do zapisania — lista się zmieniła."
        elif form.get("all"):
            saved = f"Potwierdzone: {count} tr. w {len(groups)} gr."
        else:
            g = groups[0]
            if new is None or new == g.key.category_id:
                saved = f"{g.label}: {count} tr. → {g.category}"
            else:
                name = taxonomy.all_categories(conn)[new].name
                saved = (
                    f"{g.label}: {count} tr. → {name}. Pamięć dla tego "
                    "sprzedawcy wyłączona — jego pozostałe pozycje wróciły do kolejki."
                )
        return panel.partial(
            request,
            "_review_learned.html",
            learned=review.learned(conn, d, m),
            direction=d,
            month=m,
            open=True,
            saved=saved,
            oob=True,
            inbox_count=len(panel.service.inbox()),
            queued=queued(m),
            cov=coverage(m),
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
            try:
                shown = form_rule(form, default_rule(g))
            except RuleError:
                shown = default_rule(g)
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
                make_rule=use_rule,
                **conditions_context(conn, shown, RULE),
            )

        # reguła: pozycje wybierają warunki; ręcznie: zaznaczone pola wyboru
        use_rule = requested(form)
        if cid is None:
            return fail("Wybierz podkategorię.")
        if not use_rule and not selected:
            return fail("Zaznacz co najmniej jedną transakcję.")
        if not use_rule and not selected <= {i.id for i in g.items}:
            return fail("Lista transakcji się zmieniła — odśwież stronę.")
        caught: Counter[str] = Counter()
        try:
            if use_rule:
                groups = review.all_groups(conn)
                facts = queue_facts(conn, groups)
                candidate = form_rule(form, default_rule(g))
                cond = check_rule(conn, g, candidate, facts)
                caught = elsewhere(groups, g, cond, facts)
                count = len(caught_ids(g.items, cond, facts))
                decided = closed_merchants(groups, cond, facts)
            else:
                count = len(selected)
                decided = {(i.merchant, g.key.direction) for i in g.items if i.id in selected}
            with ledger.transaction(conn):
                if use_rule:
                    rules.save(conn, replace(candidate, category_id=cid, conditions=cond))
                else:
                    for txn_id in sorted(selected):
                        engine.set_manual(conn, txn_id, cid)
                for merchant, d in sorted(decided):
                    suggest.decide(conn, merchant, d, cid)
                changed = engine.recategorize(conn)
        except (RuleError, TaxonomyError) as exc:
            return fail(str(exc))
        name = taxonomy.all_categories(conn)[cid].name
        rest = review.group(conn, g.key, m)
        learned = review.learned(conn, g.key.direction, m)
        took = {i.id for lg in learned for i in lg.items} & {i.id for i in g.items}
        return panel.partial(
            request,
            "_review_saved.html",
            g=g,
            rest=rest,
            learned=learned,
            learned_took=len(took),
            direction=g.key.direction,
            gid=gid,
            rule=use_rule,
            category=name,
            count=count,
            caught=caught,
            changed=changed,
            inbox_count=len(panel.service.inbox()),
            queued=queued(m),
            cov=coverage(m),
            month=m,
            tree=taxonomy.tree(conn),
            **(conditions_context(conn, default_rule(rest), RULE) if rest else {}),
        )

    return r
