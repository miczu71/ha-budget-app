"""Ekran Import CSV: eksport z Millenetu, raport L0–L3, mapowanie numerów kart."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response

from budget import ledger, report
from budget.csv_import import CsvFormatError
from budget.web.common import Panel
from budget.web.routes_bank import MAX_UPLOAD


def router(panel: Panel) -> APIRouter:
    r = APIRouter()
    service, conn = panel.service, panel.conn

    def unmapped_numbers() -> list[dict[str, Any]]:
        return [
            {"number": r["number"], "masked": f"…{r['number'][-4:]}", "rows": r["n"]}
            for r in conn.execute(
                "SELECT number, count(*) AS n FROM csv_row WHERE status = 'unmapped' "
                "GROUP BY number ORDER BY number"
            )
        ]

    @r.get("/import", response_class=HTMLResponse)
    async def import_page(request: Request) -> HTMLResponse:
        return panel.render(
            request,
            "import.html",
            rep=report.build(conn),
            unmapped=unmapped_numbers(),
            cards=conn.execute("SELECT * FROM account WHERE kind = 'card' ORDER BY id").fetchall(),
            batches=conn.execute(
                "SELECT * FROM import_batch WHERE source = 'csv' ORDER BY id DESC LIMIT 10"
            ).fetchall(),
        )

    @r.post("/import")
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
            return panel.redirect(
                request, "/import", f"Plik nie wygląda na eksport Millenetu: {exc}", "error"
            )
        await service.refresh()
        reasons = ", ".join(sorted({r for _, r in stats.skipped}))
        return panel.redirect(
            request,
            "/import",
            f"Zaimportowano: wierszy {stats.total}, nowych {stats.new}"
            + (f", pominiętych {len(stats.skipped)} ({reasons})" if stats.skipped else ""),
        )

    @r.post("/import/map")
    async def map_number(
        request: Request, number: str = Form(...), account_id: int = Form(...)
    ) -> Response:
        valid = {r["id"] for r in conn.execute("SELECT id FROM account WHERE kind = 'card'")}
        known = {n["number"] for n in unmapped_numbers()}
        if account_id not in valid or number not in known:
            return panel.redirect(request, "/import", "Nieznany numer albo konto.", "error")
        with ledger.transaction(conn):
            ledger.map_csv_number(conn, number, account_id)
            ledger.rebuild_derived(conn)
        await service.refresh()
        return panel.redirect(
            request, "/import", f"Numer …{number[-4:]} przypisany do konta #{account_id}."
        )

    return r
