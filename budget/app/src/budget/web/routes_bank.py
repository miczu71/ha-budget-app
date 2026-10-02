"""Ekran Bank: klucz, przeniesienie sesji z CLI, połączenie banku (SCA)."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response

from budget import sessions
from budget.eb_client import EBAuthError, EBError, load_private_key
from budget.service import ServiceError
from budget.web.common import Panel
from budget.web.routes_status import psu_from_request

log = logging.getLogger(__name__)
MAX_UPLOAD = 20 * 1024 * 1024


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    service, conn = panel.service, panel.conn

    def render_bank(request: Request, **extra: str) -> HTMLResponse:
        record = sessions.current(conn)
        return panel.render(
            request,
            "bank.html",
            record=record,
            days_left=record.days_left() if record else None,
            accounts=record.accounts if record else [],
            key_present=service.settings.private_key_path.is_file(),
            app_id=service.settings.eb_application_id,
            pending=sessions.pending_auth(conn),
            aspsp=service.settings.aspsp_name,
            missing=service.missing_config(),
            **extra,
        )

    @r.get("/bank", response_class=HTMLResponse)
    async def bank(request: Request) -> HTMLResponse:
        return render_bank(request)

    @r.post("/bank/key")
    async def upload_key(request: Request, file: UploadFile) -> Response:
        data = await file.read(MAX_UPLOAD)
        try:
            load_private_key(data)
        except ValueError:
            return panel.redirect(
                request, "/bank", "To nie jest klucz prywatny RSA w formacie PEM.", "error"
            )
        path = service.settings.private_key_path
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        path.chmod(0o600)
        log.info("Klucz prywatny Enable Banking zapisany")
        return panel.redirect(request, "/bank", "Klucz zapisany.")

    @r.post("/bank/session")
    async def upload_session(request: Request, file: UploadFile) -> Response:
        data = await file.read(MAX_UPLOAD)
        try:
            async with service.eb_client() as eb:
                record = await sessions.import_session_file(conn, eb, data)
        except (ServiceError, sessions.SessionError) as exc:
            return panel.redirect(request, "/bank", str(exc), "error")
        except EBError as exc:
            return panel.redirect(
                request, "/bank", f"Enable Banking: {exc.status} {exc.code or ''}", "error"
            )
        await service.refresh()
        return panel.redirect(
            request,
            "/bank",
            f"Sesja przeniesiona: {record.aspsp}, kont {len(record.accounts)}, "
            f"zgoda ważna {record.days_left()} dni.",
        )

    @r.post("/bank/auth")
    async def auth_start(request: Request, aspsp: str = Form(...)) -> Response:
        try:
            async with service.eb_client() as eb:
                url = await sessions.start_auth(
                    conn,
                    eb,
                    aspsp_name=aspsp,
                    country=service.settings.aspsp_country,
                    redirect_url=service.settings.eb_redirect_url,
                )
        except (ServiceError, sessions.SessionError, LookupError) as exc:
            return panel.redirect(request, "/bank", str(exc), "error")
        except EBError as exc:
            return panel.redirect(
                request, "/bank", f"Enable Banking: {exc.status} {exc.code or ''}", "error"
            )
        panel.flash.append(
            ("ok", "Link do banku gotowy — otwórz go, przejdź SCA i wklej adres zwrotny.")
        )
        return render_bank(request, auth_url=url)

    @r.post("/bank/auth/finish")
    async def auth_finish(request: Request, pasted: str = Form(...)) -> Response:
        try:
            async with service.eb_client() as eb:
                record = await sessions.finish_auth(conn, eb, pasted.strip())
        except (ServiceError, sessions.SessionError, EBAuthError) as exc:
            return panel.redirect(request, "/bank", str(exc), "error")
        except EBError as exc:
            return panel.redirect(
                request, "/bank", f"Enable Banking: {exc.status} {exc.code or ''}", "error"
            )
        # Pełne okno 90 dni z nagłówkami PSU — użytkownik jest obecny, limit nie obowiązuje
        try:
            result = await service.sync("backfill", psu=psu_from_request(request), full=True)
            note = f"pobrano {result.new} transakcji ({result.status})"
        except ServiceError as exc:
            note = f"pobieranie historii nieudane: {exc}"
        return panel.redirect(
            request,
            "/bank",
            f"Bank połączony: {record.aspsp}, kont {len(record.accounts)}; {note}.",
        )

    return r
