"""Ekran Transakcje: lista z filtrami, kategoria w wierszu (zmiana ręczna przez htmx).

Data na liście i w filtrach to data transakcji (bez niej: księgowania) — ta sama, po której
ekran „Wydatki” przypisuje transakcję do miesiąca, więc linki z „Wydatków” pokazują te same
pozycje, które złożyły się na sumę.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from budget import ledger
from budget.categorize import engine, taxonomy
from budget.categorize.taxonomy import TaxonomyError
from budget.web.common import Panel

PAGE_SIZE = 50
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
        account: int | None = None,
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
        if account:
            where.append("t.account_id = ?")
            params.append(account)
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
        if q:
            where.append(
                "(t.description LIKE ? ESCAPE '\\' OR t.counterparty_name LIKE ? ESCAPE '\\' "
                "OR t.merchant LIKE ? ESCAPE '\\')"
            )
            like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            params += [like, like, like]
        sql_where = " AND ".join(where)
        joins = "LEFT JOIN category c ON c.id = t.category_id"
        total = conn.execute(
            f"SELECT count(*) FROM txn t {joins} WHERE {sql_where}", params
        ).fetchone()[0]
        page = max(page, 1)
        rows = conn.execute(
            f"SELECT t.*, {TXN_DATE} AS day, a.display_name, a.product, "
            f"a.kind AS account_kind, c.name AS category_name, p.name AS category_main "
            f"FROM txn t JOIN account a ON a.id = t.account_id {joins} "
            f"LEFT JOIN category p ON p.id = c.parent_id WHERE {sql_where} "
            f"ORDER BY {TXN_DATE} DESC, t.id DESC LIMIT ? OFFSET ?",
            [*params, PAGE_SIZE, (page - 1) * PAGE_SIZE],
        ).fetchall()
        return panel.render(
            request,
            "transactions.html",
            rows=rows,
            total=total,
            page=page,
            pages=max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1),
            accounts=conn.execute("SELECT * FROM account ORDER BY id").fetchall(),
            kinds=[r[0] for r in conn.execute("SELECT DISTINCT kind FROM txn ORDER BY 1")],
            tree=taxonomy.tree(conn),
            f={
                "account": account,
                "date_from": date_from or "",
                "date_to": date_to or "",
                "kind": kind or "",
                "category": category or "",
                "direction": direction or "",
                "q": q or "",
            },
        )

    @r.get("/transactions/{txn_id}/category", response_class=HTMLResponse)
    async def category_form(request: Request, txn_id: int, cancel: int = 0) -> HTMLResponse:
        t = txn_row(conn, txn_id)
        if t is None:
            return HTMLResponse("Nie ma takiej transakcji.", 404)
        return panel.partial(
            request, "_txn_category.html", t=t, editing=not cancel, tree=taxonomy.tree(conn)
        )

    @r.post("/transactions/{txn_id}/category", response_class=HTMLResponse)
    async def set_category(
        request: Request, txn_id: int, category_id: str = Form("")
    ) -> HTMLResponse:
        error = None
        try:
            with ledger.transaction(conn):
                engine.set_manual(conn, txn_id, int(category_id) if category_id else None)
                engine.recategorize(conn)
        except (TaxonomyError, ValueError) as exc:
            error = str(exc)
        t = txn_row(conn, txn_id)
        if t is None:
            return HTMLResponse("Nie ma takiej transakcji.", 404)
        return panel.partial(
            request,
            "_txn_category.html",
            t=t,
            editing=False,
            error=error,
            suggest=error is None and t["category_source"] == "manual" and bool(t["merchant"]),
        )

    return r
