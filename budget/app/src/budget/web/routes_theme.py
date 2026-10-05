"""Wybór motywu wyglądu (M13 E1b): zapis w magazynie kv, powrót na tę samą stronę."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response

from budget.storage import db
from budget.web.common import THEME_KEY, THEMES, Panel


def router(panel: Panel) -> APIRouter:
    r = APIRouter()

    @r.post("/theme")
    async def set_theme(request: Request, theme: str = Form(""), back: str = Form("/")) -> Response:
        # tylko ścieżka wewnątrz panelu — bez adresów zewnętrznych i bez `//host`
        target = back if back.startswith("/") and not back.startswith("//") else "/"
        if theme not in THEMES:
            return panel.redirect(request, target, "Nieznany motyw wyglądu.", "error")
        db.kv_set(panel.conn, THEME_KEY, theme)
        return panel.redirect(request, target)

    return r
