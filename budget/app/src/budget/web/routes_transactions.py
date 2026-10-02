"""Ekran Transakcje: lista z filtrami."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from budget.web.common import Panel

PAGE_SIZE = 50


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    conn = panel.conn

    @r.get("/transactions", response_class=HTMLResponse)
    async def transactions(
        request: Request,
        account: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        kind: str | None = None,
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
                    where.append(f"t.booking_date {op} ?")
                except ValueError:
                    pass
        if kind:
            where.append("t.kind = ?")
            params.append(kind)
        if q:
            where.append(
                "(t.description LIKE ? ESCAPE '\\' OR t.counterparty_name LIKE ? ESCAPE '\\')"
            )
            like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            params += [like, like]
        sql_where = " AND ".join(where)
        total = conn.execute(f"SELECT count(*) FROM txn t WHERE {sql_where}", params).fetchone()[0]
        page = max(page, 1)
        rows = conn.execute(
            f"SELECT t.*, a.display_name, a.product, a.kind AS account_kind FROM txn t "
            f"JOIN account a ON a.id = t.account_id WHERE {sql_where} "
            f"ORDER BY t.booking_date DESC, t.id DESC LIMIT ? OFFSET ?",
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
            f={
                "account": account,
                "date_from": date_from or "",
                "date_to": date_to or "",
                "kind": kind or "",
                "q": q or "",
            },
        )

    return r
