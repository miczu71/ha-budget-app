"""Ekran Reguły: lista reguł, edytor z podglądem na żywo, słownik sieci, kategorie.

Każdy zapis przelicza kategorie całej księgi (`engine.recategorize`) — podgląd pokazuje skutek
przed zapisem, więc osobnego „zastosuj do historii” nie ma.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response
from starlette.datastructures import FormData

from budget import ledger
from budget.categorize import engine, merchants, rules, taxonomy
from budget.categorize.rules import Conditions, Rule, RuleError, TextCondition
from budget.categorize.taxonomy import TaxonomyError
from budget.normalize import fold, matches_all, search_words
from budget.web.common import Panel


@dataclass
class DictionaryGroup:
    name: str  # marka albo „(słowa ogólne)”
    slug: str
    category: str
    patterns: list[str] = field(default_factory=list)
    hits: int = 0


def _int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def rule_from_form(form: FormData) -> Rule:
    """Pola formularza → reguła (walidacja w `rules.validate`)."""
    text = []
    for i in range(rules.MAX_TEXT_CONDITIONS):
        value = str(form.get(f"value_{i}") or "")
        if value.strip():
            text.append(
                TextCondition(
                    str(form.get(f"field_{i}") or "merchant"),
                    str(form.get(f"op_{i}") or "contains"),
                    value,
                )
            )
    category = _int(form.get("category_id"))
    return Rule(
        id=_int(form.get("id")),
        category_id=category if category is not None else 0,
        conditions=Conditions(
            text=tuple(text),
            account_id=_int(form.get("account_id")),
            kind=str(form.get("kind") or "") or None,
            direction=str(form.get("direction") or "") or None,
            amount_min=rules.parse_amount(str(form.get("amount_min") or "")),
            amount_max=rules.parse_amount(str(form.get("amount_max") or "")),
        ),
        rename=str(form.get("rename") or "") or None,
        enabled=form.get("enabled") is not None or form.get("id") is None,
    )


def describe(rule: Rule, accounts: dict[int, str]) -> str:
    """Warunki reguły jednym zdaniem (lista w panelu)."""
    c = rule.conditions
    parts = [f"{rules.TEXT_FIELDS[t.field]} {rules.OPS[t.op]} „{t.value}”" for t in c.text]
    if c.account_id is not None:
        parts.append(f"konto {accounts.get(c.account_id, '#' + str(c.account_id))}")
    if c.kind:
        parts.append(f"typ {c.kind}")
    if c.direction:
        parts.append(rules.DIRECTIONS[c.direction])
    if c.amount_min is not None:
        parts.append(f"kwota ≥ {c.amount_min}")
    if c.amount_max is not None:
        parts.append(f"kwota ≤ {c.amount_max}")
    return " i ".join(parts)


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn

    def accounts() -> dict[int, str]:
        return {
            int(a["id"]): a["display_name"] or a["product"] or f"#{a['id']}"
            for a in conn.execute("SELECT * FROM account ORDER BY id")
        }

    def form_context(rule: Rule, **extra: Any) -> dict[str, Any]:
        text = list(rule.conditions.text)
        text += [TextCondition("merchant", "contains", "")] * (
            rules.MAX_TEXT_CONDITIONS - len(text)
        )
        return {
            "rule": rule,
            "text": text,
            "tree": taxonomy.tree(conn),
            "accounts": accounts(),
            "kinds": [r[0] for r in conn.execute("SELECT DISTINCT kind FROM txn ORDER BY 1")],
            "fields": rules.TEXT_FIELDS,
            "ops": rules.OPS,
            "directions": rules.DIRECTIONS,
            **extra,
        }

    def recategorize() -> int:
        with ledger.transaction(conn):
            return engine.recategorize(conn)

    def back_to_rules(form: FormData) -> str:
        """Lista reguł z filtrem, z którym użytkownik kliknął akcję w wierszu."""
        q = str(form.get("q") or "").strip()
        return f"/rules?q={quote(q)}" if q else "/rules"

    @r.get("/rules", response_class=HTMLResponse)
    async def rules_page(request: Request, q: str = "") -> HTMLResponse:
        cats = taxonomy.all_categories(conn)
        acc = accounts()
        items: list[dict[str, Any]] = []
        for rule in rules.all_rules(conn):
            cat = cats.get(rule.category_id)
            main = cats.get(cat.parent_id) if cat and cat.parent_id else None
            text = describe(rule, acc)
            haystack = " ".join(
                [text, cat.name if cat else "", main.name if main else "", rule.rename or ""]
                + ([] if rule.enabled else ["wyłączona"])
            )
            items.append({"rule": rule, "text": text, "category": cat, "haystack": fold(haystack)})
        total = len(items)
        words = search_words(q)
        items = [it for it in items if matches_all(it["haystack"], words)]
        return panel.render(
            request, "rules.html", items=items, total=total, q=q.strip(), tab="rules"
        )

    @r.get("/rules/new", response_class=HTMLResponse)
    async def new_rule(request: Request, txn: int | None = None) -> HTMLResponse:
        rule = Rule(None, 0, Conditions(text=()))
        if txn is not None:
            t = conn.execute(
                "SELECT merchant, category_id, amount FROM txn WHERE id = ?", (txn,)
            ).fetchone()
            if t is not None and t["merchant"]:
                rule = Rule(
                    None,
                    t["category_id"] or 0,
                    Conditions(text=(TextCondition("merchant", "equals", t["merchant"]),)),
                )
        return panel.render(request, "rule_form.html", **form_context(rule), txn=txn, tab="rules")

    @r.get("/rules/{rule_id}", response_class=HTMLResponse)
    async def edit_rule(request: Request, rule_id: int) -> Response:
        rule = rules.get(conn, rule_id)
        if rule is None:
            return panel.redirect(request, "/rules", "Nie ma takiej reguły.", "error")
        return panel.render(request, "rule_form.html", **form_context(rule), tab="rules")

    @r.post("/rules/preview", response_class=HTMLResponse)
    async def preview(request: Request) -> HTMLResponse:
        try:
            form = await request.form()
            rule = rules.validate(conn, rule_from_form(form))
        except RuleError as exc:
            return panel.partial(request, "_rule_preview.html", error=str(exc))
        return panel.partial(
            request,
            "_rule_preview.html",
            p=engine.preview(conn, rule, release=_int(form.get("txn"))),
            cats=taxonomy.all_categories(conn),
        )

    @r.post("/rules/save")
    async def save(request: Request) -> Response:
        form = await request.form()
        try:
            rule = rule_from_form(form)
            with ledger.transaction(conn):
                rules.save(conn, rule)
                if (txn := _int(form.get("txn"))) is not None:
                    engine.release_manual(conn, txn, rule.category_id)
                changed = engine.recategorize(conn)
        except RuleError as exc:
            panel.flash.append(("error", str(exc)))
            return panel.render(
                request,
                "rule_form.html",
                **form_context(rule_from_form_safe(form)),
                txn=_int(form.get("txn")),
                tab="rules",
            )
        return panel.redirect(
            request, "/rules", f"Reguła zapisana; zaktualizowane transakcje: {changed}."
        )

    def rule_from_form_safe(form: FormData) -> Rule:
        try:
            return rule_from_form(form)
        except RuleError:
            return Rule(_int(form.get("id")), 0, Conditions(text=()))

    @r.post("/rules/{rule_id}/toggle")
    async def toggle(request: Request, rule_id: int) -> Response:
        back = back_to_rules(await request.form())
        rule = rules.get(conn, rule_id)
        if rule is None:
            return panel.redirect(request, back, "Nie ma takiej reguły.", "error")
        rules.set_enabled(conn, rule_id, not rule.enabled)
        changed = recategorize()
        state = "wyłączona" if rule.enabled else "włączona"
        return panel.redirect(
            request, back, f"Reguła {state}; zaktualizowane transakcje: {changed}."
        )

    @r.post("/rules/{rule_id}/move")
    async def move(request: Request, rule_id: int, step: int = Form(...)) -> Response:
        try:
            rules.move(conn, rule_id, -1 if step < 0 else 1)
        except RuleError as exc:
            return panel.redirect(request, "/rules", str(exc), "error")
        changed = recategorize()
        return panel.redirect(
            request, "/rules", f"Kolejność zmieniona; zaktualizowane transakcje: {changed}."
        )

    @r.post("/rules/{rule_id}/delete")
    async def delete(request: Request, rule_id: int) -> Response:
        back = back_to_rules(await request.form())
        rules.delete(conn, rule_id)
        changed = recategorize()
        return panel.redirect(
            request, back, f"Reguła usunięta; zaktualizowane transakcje: {changed}."
        )

    # --- słownik ----------------------------------------------------------------------------

    @r.get("/dictionary", response_class=HTMLResponse)
    async def dictionary(request: Request, q: str = "") -> HTMLResponse:
        d = merchants.builtin()
        slugs = {c.slug: c for c in taxonomy.leaves(conn).values()}
        hits = engine.dictionary_hits(conn, d)
        groups: dict[tuple[str, str], DictionaryGroup] = {}
        for e in d.entries:
            key = (e.name or "(słowa ogólne)", e.slug)
            cat = slugs.get(e.slug)
            g = groups.setdefault(key, DictionaryGroup(key[0], e.slug, cat.name if cat else e.slug))
            g.patterns.append(" ".join(e.pattern))
            g.hits += hits.get(e.order, 0)
        items = list(groups.values())
        total = len(items)
        words = search_words(q)
        items = [
            g
            for g in items
            if matches_all(fold(" ".join([g.name, g.category, *g.patterns])), words)
        ]
        items.sort(key=lambda g: (-g.hits, g.name))
        return panel.render(
            request,
            "dictionary.html",
            items=items,
            total=total,
            dict_version=d.version,
            q=q.strip(),
            tab="dictionary",
        )

    # --- kategorie --------------------------------------------------------------------------

    @r.get("/categories", response_class=HTMLResponse)
    async def categories(request: Request) -> HTMLResponse:
        counts: dict[int, int] = defaultdict(int)
        for row in conn.execute(
            "SELECT category_id, count(*) AS n FROM txn WHERE category_id IS NOT NULL "
            "GROUP BY category_id"
        ):
            counts[int(row["category_id"])] = int(row["n"])
        return panel.render(
            request,
            "categories.html",
            tree=taxonomy.tree(conn),
            counts=counts,
            groups=taxonomy.FLEX_LABELS,
            tab="categories",
        )

    @r.post("/categories/add")
    async def add_category(
        request: Request, parent_id: int = Form(...), name: str = Form("")
    ) -> Response:
        try:
            taxonomy.add_subcategory(conn, parent_id, name)
        except TaxonomyError as exc:
            return panel.redirect(request, "/categories", str(exc), "error")
        return panel.redirect(request, "/categories", f"Dodano podkategorię „{name.strip()}”.")

    @r.post("/categories/{category_id}/rename")
    async def rename_category(request: Request, category_id: int, name: str = Form("")) -> Response:
        try:
            taxonomy.rename(conn, category_id, name)
        except TaxonomyError as exc:
            return panel.redirect(request, "/categories", str(exc), "error")
        return panel.redirect(request, "/categories", "Zmieniono nazwę.")

    @r.post("/categories/add-main")
    async def add_main_category(request: Request, name: str = Form("")) -> Response:
        try:
            taxonomy.add_main(conn, name)
        except TaxonomyError as exc:
            return panel.redirect(request, "/categories", str(exc), "error")
        return panel.redirect(request, "/categories", f"Dodano kategorię główną „{name.strip()}”.")

    @r.post("/categories/{category_id}/move")
    async def move_category(
        request: Request, category_id: int, parent_id: int = Form(...)
    ) -> Response:
        try:
            taxonomy.move(conn, category_id, parent_id)
        except TaxonomyError as exc:
            return panel.redirect(request, "/categories", str(exc), "error")
        cats = taxonomy.all_categories(conn)
        return panel.redirect(
            request,
            "/categories",
            f"Przeniesiono „{cats[category_id].name}” do „{cats[parent_id].name}” "
            "razem z transakcjami i regułami.",
        )

    @r.post("/categories/{category_id}/delete")
    async def delete_category(request: Request, category_id: int) -> Response:
        try:
            name = taxonomy.delete_main(conn, category_id)
        except TaxonomyError as exc:
            return panel.redirect(request, "/categories", str(exc), "error")
        return panel.redirect(request, "/categories", f"Usunięto kategorię „{name}”.")

    return r
