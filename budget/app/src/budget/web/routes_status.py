"""Ekran Status: zgoda, synchronizacja, salda, liczniki zapytań, kontrola sald."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from budget import ledger, report, sessions, sync_service
from budget.eb_client import PsuHeaders
from budget.service import ServiceError
from budget.web.common import Panel


def psu_from_request(request: Request) -> PsuHeaders:
    """Dane obecnego użytkownika do nagłówków PSU (SPEC §2.3)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else None)
    h = request.headers
    return PsuHeaders(
        ip_address=ip or None,
        user_agent=h.get("user-agent"),
        accept=h.get("accept"),
        accept_language=h.get("accept-language"),
        accept_encoding=h.get("accept-encoding"),
    )


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    service, conn = panel.service, panel.conn

    def status_context() -> dict[str, Any]:
        today = service.now().date()
        record = sessions.current(conn)
        names = {r["id"]: r for r in conn.execute("SELECT * FROM account")}
        requests = [
            {**dict(r), "account": names.get(r["account_id"])}
            for r in sync_service.requests_today(conn, today)
        ]
        balances = conn.execute(
            "SELECT a.id, a.display_name, a.product, a.kind, a.currency, b.balance_type, "
            "b.amount, b.fetched_at FROM account a JOIN balance_snapshot b ON b.account_id = a.id "
            "WHERE b.fetched_at = (SELECT max(fetched_at) FROM balance_snapshot "
            "WHERE account_id = a.id) ORDER BY a.id, b.balance_type"
        ).fetchall()
        return {
            "record": record,
            "days_left": record.days_left() if record else None,
            "log": sync_service.recent(conn),
            "requests": requests,
            "limit": sync_service.DAILY_LIMIT,
            "balances": balances,
            "checks": [report.balance_line(c) for c in ledger.check_balances(conn)],
            "missing": service.missing_config(),
            "manual_needed": service.manual_sync_needed(),
            "busy": service.lock.locked(),
        }

    @r.get("/", response_class=HTMLResponse)
    async def status(request: Request) -> HTMLResponse:
        return panel.render(request, "status.html", **status_context())

    @r.post("/sync")
    async def sync_now(request: Request) -> Response:
        if service.lock.locked():
            return panel.redirect(request, "/", "Synchronizacja już trwa.", "warn")
        try:
            result = await service.sync("panel", psu=psu_from_request(request))
        except ServiceError as exc:
            return panel.redirect(request, "/", str(exc), "error")
        level = "ok" if result.ok else "warn" if result.status == "partial" else "error"
        text = f"Synchronizacja: {result.status}, nowych {result.new}, zapytań {result.requests}"
        if result.detail:
            text += f" — {result.detail}"
        return panel.redirect(request, "/", text, level)

    return r
