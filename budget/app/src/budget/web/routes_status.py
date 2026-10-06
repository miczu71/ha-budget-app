"""Ekran Status: zgoda, synchronizacja, salda, liczniki zapytań, kontrola sald."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget import ledger, report, sessions, summary, sync_service
from budget.ask import engine as ask
from budget.categorize import engine, learn
from budget.eb_client import PsuHeaders
from budget.service import ServiceError
from budget.storage import db
from budget.suggest import engine as suggest
from budget.suggest.client import AIError
from budget.web.common import Panel

log = logging.getLogger(__name__)


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
        chat_log = ask.log_rows(conn)
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
            "checks": [(report.balance_line(c), c) for c in panel.service.balance_memo.get(conn)],
            "missing": service.missing_config(),
            "manual_needed": service.manual_sync_needed(),
            "busy": service.lock.locked(),
            "ai": ai_context(),
            "summaries": summaries_context(),
            "learn": db.kv_get(conn, learn.EVAL_KEY),
            "learned_stats": engine.learned_stats(conn),
            "chat_log": chat_log,
            "chat_counts": Counter(e["outcome"] for e in chat_log),
        }

    def summaries_context() -> dict[str, Any]:
        today = service.now().date()
        try:
            previews = [
                summary.build(service.snapshot, k, today) for k in (summary.WEEKLY, summary.MONTHLY)
            ]
        except Exception:  # podgląd nie może zablokować ekranu Status
            log.exception("Podgląd podsumowań")
            previews = []
        return {
            "target": service.settings.summary_notify_service,
            "previews": previews,
            "sent": db.kv_get(conn, summary.SENT_KEY) or {},
        }

    def ai_context() -> dict[str, Any]:
        s = service.settings
        return {
            "enabled": s.ai_enabled,
            "model": s.ai_model,
            "limit": s.ai_daily_calls,
            "usage": suggest.usage(conn, service.now().date()),
            "stats": suggest.stats(conn) if s.ai_enabled else {},
            "eval": db.kv_get(conn, suggest.EVAL_KEY),
            "busy": service.ai_lock.locked(),
        }

    @r.get("/status", response_class=HTMLResponse)
    async def status(request: Request) -> HTMLResponse:
        return panel.render(request, "status.html", **status_context())

    @r.post("/sync")
    async def sync_now(request: Request) -> Response:
        if service.lock.locked():
            return panel.redirect(request, "/status", "Synchronizacja już trwa.", "warn")
        try:
            result = await service.sync("panel", psu=psu_from_request(request))
        except ServiceError as exc:
            return panel.redirect(request, "/status", str(exc), "error")
        level = "ok" if result.ok else "warn" if result.status == "partial" else "error"
        text = f"Synchronizacja: {result.status}, nowych {result.new}, zapytań {result.requests}"
        if result.detail:
            text += f" — {result.detail}"
        return panel.redirect(request, "/status", text, level)

    @r.post("/summary/send")
    async def summary_send(request: Request, kind: str = Form(...)) -> Response:
        if kind not in (summary.WEEKLY, summary.MONTHLY):
            return panel.redirect(request, "/status", "Nieznane podsumowanie.", "error")
        try:
            await service.send_summary(summary.build(service.snapshot, kind, service.now().date()))
        except ServiceError as exc:
            return panel.redirect(request, "/status", str(exc), "error")
        return panel.redirect(request, "/status", "Podsumowanie wysłane.")

    @r.post("/status/reconcile-base")
    async def reconcile_base(request: Request, account_id: int = Form(...)) -> Response:
        at = ledger.set_reconcile_base(conn, account_id)
        if at is None:
            return panel.redirect(request, "/status", "Brak migawki salda dla tego konta.", "error")
        return panel.redirect(
            request, "/status", f"Konto #{account_id}: baza kontroli salda od {at[:16]}."
        )

    @r.post("/ai/run")
    async def ai_run(request: Request) -> Response:
        if not service.settings.ai_enabled:
            return panel.redirect(request, "/status", "Podpowiedzi AI są wyłączone.", "warn")
        if service.ai_lock.locked():
            return panel.redirect(request, "/status", "Podpowiedzi AI już się liczą.", "warn")
        res = await service.suggest()
        text = f"Podpowiedzi AI: wywołań {res.calls}, zapisanych {res.stored}, czeka {res.waiting}"
        if res.error:
            return panel.redirect(request, "/status", f"{text} — {res.error}", "error")
        return panel.redirect(request, "/status", text, "ok" if res.calls else "warn")

    @r.post("/learn/eval")
    async def learn_eval(request: Request) -> Response:
        out = await learn.evaluate(conn)
        return panel.redirect(
            request, "/status", f"Pomiar kategoryzacji: {out['months']} miesięcy historii", "ok"
        )

    @r.post("/ai/eval")
    async def ai_eval(request: Request) -> Response:
        if service.ai_lock.locked():
            return panel.redirect(request, "/status", "Podpowiedzi AI już się liczą.", "warn")
        try:
            async with service.ai_lock:
                out = await suggest.evaluate(conn, service.settings, service.now().date())
        except AIError as exc:
            return panel.redirect(request, "/status", f"Pomiar trafności: {exc}", "error")
        return panel.redirect(request, "/status", f"Pomiar trafności: {out['n']} sprzedawców", "ok")

    return r
