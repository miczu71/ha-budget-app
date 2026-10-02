"""Panel add-onu (Ingress): Status, Bank, Import CSV, Konta, Transakcje.

- Ingress: prefiks z nagłówka `X-Ingress-Path` trafia do szablonów jako `base`; żądania spoza
  proxy Supervisora (172.30.32.2) są odrzucane (poza trybem dev).
- Mobile WebView (aplikacja HA) agresywnie cache'uje: HTML i odpowiedzi `no-store`, statyki
  z `?v=<wersja>` i `immutable`, wersja widoczna w nawigacji.
- Wszystkie endpointy są `async` — działają w pętli usługi (jedno połączenie SQLite).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from budget import __version__, ledger, report, sessions, sync_service
from budget.csv_import import CsvFormatError
from budget.eb_client import EBAuthError, EBError, PsuHeaders, load_private_key
from budget.logging_utils import mask_iban
from budget.service import Service, ServiceError

log = logging.getLogger(__name__)

HERE = Path(__file__).parent
INGRESS_PROXY = "172.30.32.2"
PAGE_SIZE = 50
MAX_UPLOAD = 20 * 1024 * 1024
KIND_LABELS = {
    "card": "karta",
    "card_refund": "zwrot (karta)",
    "blik": "BLIK",
    "blik_refund": "zwrot BLIK",
    "phone_transfer": "przelew na telefon",
    "transfer_in": "przelew przych.",
    "transfer_out": "przelew wych.",
    "standing_order": "zlecenie stałe",
    "direct_debit": "polecenie zapłaty",
    "cash": "gotówka",
    "loan": "kredyt",
    "card_repayment": "spłata karty",
    "fee": "opłata",
    "other": "inne",
}


ACCOUNT_KINDS = {
    "current": "rachunek",
    "card": "karta kredytowa",
    "fx": "rachunek walutowy",
    "savings": "oszczędnościowe",
    "other": "inne",
}


def fmt_money(value: Any, currency: str | None = None) -> str:
    """`-1234.5` → `−1 234,50 zł` (polski zapis, twarde spacje)."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return "—"
    sign = "−" if amount < 0 else ""
    whole, _, frac = f"{abs(amount):.2f}".partition(".")
    groups: list[str] = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    symbol = {"PLN": "zł", "EUR": "€", None: ""}.get(currency, currency or "")
    return f"{sign}{' '.join(groups)},{frac} {symbol}".rstrip()


def fmt_ts(value: str | None, tz: Any) -> str:
    if not value:
        return "—"
    return datetime.fromisoformat(value).astimezone(tz).strftime("%d.%m %H:%M")


def fmt_date(value: str | None) -> str:
    """`2026-10-01` → `01.10.2026`."""
    if not value:
        return "—"
    try:
        return date.fromisoformat(value[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return value


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


def create_app(service: Service, *, dev: bool = False) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["money"] = fmt_money
    templates.env.filters["ts"] = lambda v: fmt_ts(v, service.tz)
    templates.env.filters["iban"] = mask_iban
    templates.env.filters["pldate"] = fmt_date
    templates.env.globals["version"] = __version__
    templates.env.globals["kind_labels"] = KIND_LABELS
    templates.env.globals["account_kinds"] = ACCOUNT_KINDS
    flash: list[tuple[str, str]] = []  # jeden użytkownik — komunikat do następnego widoku

    @app.middleware("http")
    async def ingress(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        peer = request.client.host if request.client else ""
        if not dev and peer != INGRESS_PROXY:
            return Response("Dostęp tylko przez panel Home Assistant (Ingress).", 403)
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-store"
        return response

    def base(request: Request) -> str:
        return request.headers.get("x-ingress-path", "").rstrip("/")

    def render(request: Request, name: str, **ctx: Any) -> HTMLResponse:
        messages = list(flash)
        flash.clear()
        return templates.TemplateResponse(
            request,
            name,
            {
                "base": base(request),
                "messages": messages,
                "page": name.removesuffix(".html"),
                **ctx,
            },
        )

    def redirect(
        request: Request, path: str, message: str | None = None, level: str = "ok"
    ) -> Response:
        if message:
            flash.append((level, message))
        return RedirectResponse(f"{base(request)}{path}", status_code=303)

    conn = service.conn

    # --- Status ---------------------------------------------------------------------------

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

    @app.get("/", response_class=HTMLResponse)
    async def status(request: Request) -> HTMLResponse:
        return render(request, "status.html", **status_context())

    @app.post("/sync")
    async def sync_now(request: Request) -> Response:
        if service.lock.locked():
            return redirect(request, "/", "Synchronizacja już trwa.", "warn")
        try:
            result = await service.sync("panel", psu=psu_from_request(request))
        except ServiceError as exc:
            return redirect(request, "/", str(exc), "error")
        level = "ok" if result.ok else "warn" if result.status == "partial" else "error"
        text = f"Synchronizacja: {result.status}, nowych {result.new}, zapytań {result.requests}"
        if result.detail:
            text += f" — {result.detail}"
        return redirect(request, "/", text, level)

    # --- Bank ----------------------------------------------------------------------------

    @app.get("/bank", response_class=HTMLResponse)
    async def bank(request: Request) -> HTMLResponse:
        record = sessions.current(conn)
        return render(
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
        )

    @app.post("/bank/key")
    async def upload_key(request: Request, file: UploadFile) -> Response:
        data = await file.read(MAX_UPLOAD)
        try:
            load_private_key(data)
        except ValueError:
            return redirect(
                request, "/bank", "To nie jest klucz prywatny RSA w formacie PEM.", "error"
            )
        path = service.settings.private_key_path
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        path.chmod(0o600)
        log.info("Klucz prywatny Enable Banking zapisany")
        return redirect(request, "/bank", "Klucz zapisany.")

    @app.post("/bank/session")
    async def upload_session(request: Request, file: UploadFile) -> Response:
        data = await file.read(MAX_UPLOAD)
        try:
            async with service.eb_client() as eb:
                record = await sessions.import_session_file(conn, eb, data)
        except (ServiceError, sessions.SessionError) as exc:
            return redirect(request, "/bank", str(exc), "error")
        except EBError as exc:
            return redirect(
                request, "/bank", f"Enable Banking: {exc.status} {exc.code or ''}", "error"
            )
        await service.refresh()
        return redirect(
            request,
            "/bank",
            f"Sesja przeniesiona: {record.aspsp}, kont {len(record.accounts)}, "
            f"zgoda ważna {record.days_left()} dni.",
        )

    @app.post("/bank/auth")
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
            return redirect(request, "/bank", str(exc), "error")
        except EBError as exc:
            return redirect(
                request, "/bank", f"Enable Banking: {exc.status} {exc.code or ''}", "error"
            )
        flash.append(("ok", "Link do banku gotowy — otwórz go, przejdź SCA i wklej adres zwrotny."))
        return render_bank_with_link(request, url)

    def render_bank_with_link(request: Request, url: str) -> Response:
        record = sessions.current(conn)
        return render(
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
            auth_url=url,
        )

    @app.post("/bank/auth/finish")
    async def auth_finish(request: Request, pasted: str = Form(...)) -> Response:
        try:
            async with service.eb_client() as eb:
                record = await sessions.finish_auth(conn, eb, pasted.strip())
        except (ServiceError, sessions.SessionError, EBAuthError) as exc:
            return redirect(request, "/bank", str(exc), "error")
        except EBError as exc:
            return redirect(
                request, "/bank", f"Enable Banking: {exc.status} {exc.code or ''}", "error"
            )
        # Pełne okno 90 dni z nagłówkami PSU — użytkownik jest obecny, limit nie obowiązuje
        try:
            result = await service.sync("backfill", psu=psu_from_request(request), full=True)
            note = f"pobrano {result.new} transakcji ({result.status})"
        except ServiceError as exc:
            note = f"pobieranie historii nieudane: {exc}"
        return redirect(
            request,
            "/bank",
            f"Bank połączony: {record.aspsp}, kont {len(record.accounts)}; {note}.",
        )

    # --- Import CSV ----------------------------------------------------------------------

    def unmapped_numbers() -> list[dict[str, Any]]:
        return [
            {"number": r["number"], "masked": f"…{r['number'][-4:]}", "rows": r["n"]}
            for r in conn.execute(
                "SELECT number, count(*) AS n FROM csv_row WHERE status = 'unmapped' "
                "GROUP BY number ORDER BY number"
            )
        ]

    @app.get("/import", response_class=HTMLResponse)
    async def import_page(request: Request) -> HTMLResponse:
        return render(
            request,
            "import.html",
            rep=report.build(conn),
            unmapped=unmapped_numbers(),
            cards=conn.execute("SELECT * FROM account WHERE kind = 'card' ORDER BY id").fetchall(),
            batches=conn.execute(
                "SELECT * FROM import_batch WHERE source = 'csv' ORDER BY id DESC LIMIT 10"
            ).fetchall(),
        )

    @app.post("/import")
    async def import_csv(request: Request, file: UploadFile) -> Response:
        data = await file.read(MAX_UPLOAD)
        try:
            stats = ledger.ingest_csv(
                conn,
                data,
                file_name=file.filename or "upload.csv",
                fetched_at=datetime.now(service.tz).isoformat(timespec="seconds"),
            )
        except CsvFormatError as exc:
            return redirect(
                request, "/import", f"Plik nie wygląda na eksport Millenetu: {exc}", "error"
            )
        await service.refresh()
        reasons = ", ".join(sorted({r for _, r in stats.skipped}))
        return redirect(
            request,
            "/import",
            f"Zaimportowano: wierszy {stats.total}, nowych {stats.new}"
            + (f", pominiętych {len(stats.skipped)} ({reasons})" if stats.skipped else ""),
        )

    @app.post("/import/map")
    async def map_number(
        request: Request, number: str = Form(...), account_id: int = Form(...)
    ) -> Response:
        valid = {r["id"] for r in conn.execute("SELECT id FROM account WHERE kind = 'card'")}
        known = {n["number"] for n in unmapped_numbers()}
        if account_id not in valid or number not in known:
            return redirect(request, "/import", "Nieznany numer albo konto.", "error")
        with ledger.transaction(conn):
            ledger.map_csv_number(conn, number, account_id)
            ledger.relink_csv(conn)
            ledger.rebuild_links(conn)
        await service.refresh()
        return redirect(
            request, "/import", f"Numer …{number[-4:]} przypisany do konta #{account_id}."
        )

    # --- Konta ---------------------------------------------------------------------------

    @app.get("/accounts", response_class=HTMLResponse)
    async def accounts(request: Request) -> HTMLResponse:
        return render(request, "accounts.html", rep=report.build(conn))

    @app.post("/accounts/{account_id}")
    async def save_account(
        request: Request,
        account_id: int,
        display_name: str = Form(""),
        include_in_budget: str | None = Form(None),
    ) -> Response:
        name = display_name.strip()[:60] or None
        cur = conn.execute(
            "UPDATE account SET display_name = ?, include_in_budget = ? WHERE id = ?",
            (name, int(include_in_budget is not None), account_id),
        )
        if not cur.rowcount:
            return redirect(request, "/accounts", "Nie ma takiego konta.", "error")
        await service.refresh()
        return redirect(request, "/accounts", "Zapisano.")

    # --- Transakcje ----------------------------------------------------------------------

    @app.get("/transactions", response_class=HTMLResponse)
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
        return render(
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

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app
