"""Ekran Transakcje: lista z filtrami, kategoria w wierszu (zmiana przez htmx).

Zapis kategorii domyślnie ustawia kategorię ręczną tylko tej transakcji. „Utwórz regułę”
rozwija w miejscu pola warunków (jak w kolejce i edytorze Reguł, `web.rule_form`) z warunkiem
„sprzedawca równa się …” + kierunek; reguła musi objąć tę transakcję, a jej ręczna kategoria
jest zdejmowana — kategorię daje odtąd reguła (też przyszłym transakcjom).

Data na liście i w filtrach to data transakcji (bez niej: księgowania) — ta sama, po której
ekran „Wydatki” przypisuje transakcję do miesiąca, więc linki z „Wydatków” pokazują te same
pozycje, które złożyły się na sumę.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.datastructures import FormData

from budget import ledger
from budget.categorize import engine, rules, taxonomy
from budget.categorize.rules import Conditions, Rule, RuleError, TextCondition
from budget.categorize.taxonomy import TaxonomyError
from budget.normalize import search_words
from budget.recurring import series as S
from budget.recurring.series import Series
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

PAGE_SIZE = 50
# Tekst do „Szukaj”: po `fold` (funkcja SQL z storage.db) — jak reguły, bez ogonków
SEARCH_TEXT = (
    "fold(t.description || ' ' || coalesce(t.counterparty_name, '') || ' ' "
    "|| coalesce(t.merchant, ''))"
)
TXN_DATE = "coalesce(t.tx_date, t.booking_date)"
SOURCE_LABELS = {
    "manual": "ręczna",
    "rule": "reguła",
    "dictionary": "słownik",
    "kind": "typ",
    "refund": "zwrot",
}


def txn_row(conn: sqlite3.Connection, txn_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        f"SELECT t.*, {TXN_DATE} AS day, c.name AS category_name, p.name AS category_main "
        "FROM txn t LEFT JOIN category c ON c.id = t.category_id "
        "LEFT JOIN category p ON p.id = c.parent_id WHERE t.id = ?",
        (txn_id,),
    ).fetchone()
    return row


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn
    panel.templates.env.globals["source_labels"] = SOURCE_LABELS

    def category_filter(value: str, where: list[str], params: list[Any]) -> None:
        if value == "none":
            where.append("t.category_id IS NULL AND t.transfer_group IS NULL")
            return
        try:
            cid = int(value)
        except ValueError:
            return
        where.append("(t.category_id = ? OR c.parent_id = ?)")
        params += [cid, cid]

    @r.get("/transactions", response_class=HTMLResponse)
    async def transactions(
        request: Request,
        account: str | None = None,  # „wszystkie” w formularzu = pusty parametr
        date_from: str | None = None,
        date_to: str | None = None,
        kind: str | None = None,
        category: str | None = None,
        direction: str | None = None,
        q: str | None = None,
        page: int = 1,
    ) -> HTMLResponse:
        where: list[str] = ["t.status = 'BOOK'"]
        params: list[Any] = []
        account_id = int(account) if account and account.isdigit() else None
        if account_id:
            where.append("t.account_id = ?")
            params.append(account_id)
        for value, op in ((date_from, ">="), (date_to, "<=")):
            if value:
                try:
                    params.append(date.fromisoformat(value).isoformat())
                    where.append(f"{TXN_DATE} {op} ?")
                except ValueError:
                    pass
        if kind:
            where.append("t.kind = ?")
            params.append(kind)
        if category:
            category_filter(category, where, params)
        if direction == "out":
            where.append("t.amount LIKE '-%'")
        elif direction == "in":
            where.append("t.amount NOT LIKE '-%'")
        for word in search_words(q):  # każde słowo w opisie, kontrahencie albo sprzedawcy
            where.append(f"{SEARCH_TEXT} LIKE ? ESCAPE '\\'")
            escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
        sql_where = " AND ".join(where)
        joins = "LEFT JOIN category c ON c.id = t.category_id"
        total = conn.execute(
            f"SELECT count(*) FROM txn t {joins} WHERE {sql_where}", params
        ).fetchone()[0]
        page = max(page, 1)
        rows = conn.execute(
            f"SELECT t.*, {TXN_DATE} AS day, a.display_name, a.product, "
            f"a.kind AS account_kind, c.name AS category_name, p.name AS category_main, "
            f"h.name AS holder_name FROM txn t JOIN account a ON a.id = t.account_id {joins} "
            f"LEFT JOIN category p ON p.id = c.parent_id "
            f"LEFT JOIN card_holder h ON h.id = t.card_holder_id WHERE {sql_where} "
            f"ORDER BY {TXN_DATE} DESC, t.id DESC LIMIT ? OFFSET ?",
            [*params, PAGE_SIZE, (page - 1) * PAGE_SIZE],
        ).fetchall()
        live = S.all_series(conn, ("active", "ended"))
        page_txns = S.candidates(conn, [int(t["id"]) for t in rows])
        belongs: dict[int, Series] = {}
        for sid, hit in S.assign(live, page_txns).items():
            for c in hit:
                belongs[c.id] = next(x for x in live if x.id == sid)
        return panel.render(
            request,
            "transactions.html",
            rows=rows,
            series_of=belongs,
            repeatable={c.id for c in page_txns},
            total=total,
            page_no=page,  # `page` = nazwa ekranu w base.html (aktywna zakładka)
            pages=max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1),
            filtered=any((account_id, date_from, date_to, kind, category, direction, q)),
            accounts=conn.execute("SELECT * FROM account ORDER BY id").fetchall(),
            kinds=[r[0] for r in conn.execute("SELECT DISTINCT kind FROM txn ORDER BY 1")],
            tree=taxonomy.tree(conn),
            f={
                "account": account_id,
                "date_from": date_from or "",
                "date_to": date_to or "",
                "kind": kind or "",
                "category": category or "",
                "direction": direction or "",
                "q": q or "",
            },
        )

    def txn_rule(t: sqlite3.Row) -> Rule:
        """Domyślna reguła z transakcji: „sprzedawca równa się <sprzedawca>” + kierunek."""
        text = (TextCondition("merchant", "equals", t["merchant"]),) if t["merchant"] else ()
        direction = "out" if str(t["amount"]).startswith("-") else "in"
        return Rule(None, 0, Conditions(text=text, direction=direction))

    def checked_rule(t: sqlite3.Row, form: FormData) -> Rule:
        """Reguła z formularza kategorii po walidacji warunków: musi objąć tę transakcję."""
        rule = form_rule(form, txn_rule(t))
        cond = rules.clean_conditions(conn, rule.conditions)
        check_fragments(cond)
        facts = engine.facts(conn, [int(t["id"])]).get(int(t["id"]))
        if facts is None or not cond.matches(facts):
            raise RuleError("Warunki nie pasują do tej transakcji — reguła by jej nie objęła.")
        return replace(rule, conditions=cond)

    def editor(
        request: Request,
        t: sqlite3.Row,
        *,
        form: FormData | None = None,
        error: str | None = None,
        category_id: int | None = None,
    ) -> HTMLResponse:
        try:
            shown = form_rule(form, txn_rule(t))
        except RuleError:
            shown = txn_rule(t)
        return panel.partial(
            request,
            "_txn_category.html",
            t=t,
            editing=True,
            error=error,
            pick=category_id,
            make_rule=requested(form),
            tree=taxonomy.tree(conn),
            **conditions_context(conn, shown, RULE),
        )

    def leaf(form: FormData) -> int | None:
        try:
            cid = int(str(form.get("category_id") or ""))
        except ValueError:
            return None
        return cid if cid in taxonomy.leaves(conn) else None

    @r.get("/transactions/{txn_id}/category", response_class=HTMLResponse)
    async def category_form(request: Request, txn_id: int, cancel: int = 0) -> HTMLResponse:
        t = txn_row(conn, txn_id)
        if t is None:
            return HTMLResponse("Nie ma takiej transakcji.", 404)
        if cancel:
            return panel.partial(request, "_txn_category.html", t=t, editing=False)
        return editor(request, t)

    @r.post("/transactions/{txn_id}/rule-preview", response_class=HTMLResponse)
    async def rule_preview(request: Request, txn_id: int) -> HTMLResponse:
        t = txn_row(conn, txn_id)
        if t is None:
            return HTMLResponse("Nie ma takiej transakcji.", 404)
        form = await request.form()
        if not requested(form):
            return HTMLResponse("")
        try:
            rule = checked_rule(t, form)
        except RuleError as exc:
            return panel.partial(request, "_txn_rule_preview.html", error=str(exc))
        cid = leaf(form)
        ctx: dict[str, Any] = {"describe": describe(rule, accounts(conn))}
        if cid is not None:
            ctx["category"] = taxonomy.all_categories(conn)[cid]
            ctx["p"] = engine.preview(
                conn, replace(rule, category_id=cid), release=txn_id, release_any=True
            )
        return panel.partial(request, "_txn_rule_preview.html", **ctx)

    @r.post("/transactions/{txn_id}/category", response_class=HTMLResponse)
    async def set_category(request: Request, txn_id: int) -> HTMLResponse:
        t = txn_row(conn, txn_id)
        if t is None:
            return HTMLResponse("Nie ma takiej transakcji.", 404)
        form = await request.form()
        error = None
        if requested(form):
            cid = leaf(form)
            try:
                if cid is None:
                    raise RuleError("Wybierz podkategorię.")
                rule = checked_rule(t, form)
                with ledger.transaction(conn):
                    rules.save(conn, replace(rule, category_id=cid))
                    engine.set_manual(conn, txn_id, None)  # kategorię daje teraz reguła
                    engine.recategorize(conn)
            except (RuleError, TaxonomyError) as exc:
                return editor(request, t, form=form, error=str(exc), category_id=cid)
        else:
            category_id = str(form.get("category_id") or "")
            try:
                with ledger.transaction(conn):
                    engine.set_manual(conn, txn_id, int(category_id) if category_id else None)
                    engine.recategorize(conn)
            except (TaxonomyError, ValueError) as exc:
                error = str(exc)
        t = txn_row(conn, txn_id)
        if t is None:
            return HTMLResponse("Nie ma takiej transakcji.", 404)
        return panel.partial(request, "_txn_category.html", t=t, editing=False, error=error)

    return r
