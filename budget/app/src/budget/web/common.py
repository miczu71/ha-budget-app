"""Wspólne dla ekranów panelu: szablony, filtry formatujące, komunikaty, przekierowania."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from budget import __version__
from budget.categorize.rules import OPS as RULE_OPS
from budget.logging_utils import mask_iban
from budget.service import Service
from budget.spending import month_label
from budget.suggest import engine as suggest

HERE = Path(__file__).parent
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
    # grupy cyfr: wąska twarda spacja (U+202F), przed walutą: twarda spacja (U+00A0)
    return f"{sign}{'\u202f'.join(groups)},{frac}\xa0{symbol}".rstrip()


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


class Panel:
    """Stan i pomocnicze funkcje ekranów; jeden użytkownik, więc komunikat „flash” to lista."""

    def __init__(self, service: Service) -> None:
        self.service = service
        self.conn = service.conn
        self.flash: list[tuple[str, str]] = []
        t = Jinja2Templates(directory=HERE / "templates")
        t.env.filters["money"] = fmt_money
        t.env.filters["ts"] = lambda v: fmt_ts(v, service.tz)
        t.env.filters["iban"] = mask_iban
        t.env.filters["pldate"] = fmt_date
        t.env.globals["version"] = __version__
        t.env.globals["kind_labels"] = KIND_LABELS
        t.env.globals["rule_ops"] = RULE_OPS
        t.env.globals["account_kinds"] = ACCOUNT_KINDS
        t.env.globals["month_label"] = month_label
        t.env.globals["ai_candidates"] = self.ai_candidates
        self.templates = t

    def ai_candidates(self, merchant: str | None, direction: str) -> list[suggest.Candidate]:
        """Kandydaci kategorii z AI dla sprzedawcy (pusto, gdy AI wyłączone albo brak)."""
        if not merchant or not self.service.settings.ai_enabled:
            return []
        return suggest.candidates(self.conn, merchant, direction)

    @staticmethod
    def base(request: Request) -> str:
        return request.headers.get("x-ingress-path", "").rstrip("/")

    def render(self, request: Request, name: str, **ctx: Any) -> HTMLResponse:
        messages = list(self.flash)
        self.flash.clear()
        return self.templates.TemplateResponse(
            request,
            name,
            {
                "base": self.base(request),
                "messages": messages,
                "page": name.removesuffix(".html"),
                "inbox_count": len(self.service.inbox()),
                **ctx,
            },
        )

    def partial(self, request: Request, name: str, **ctx: Any) -> HTMLResponse:
        """Fragment dla htmx (bez komunikatów i bez strony bazowej)."""
        return self.templates.TemplateResponse(request, name, {"base": self.base(request), **ctx})

    def redirect(
        self, request: Request, path: str, message: str | None = None, level: str = "ok"
    ) -> Response:
        if message:
            self.flash.append((level, message))
        return RedirectResponse(f"{self.base(request)}{path}", status_code=303)
