"""Strona główna (M13): podsumowanie miesiąca — Zostało, wykresy, bilans, nadchodzące, ostatnie."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from budget import card, flex, forecast, home_layout, sessions, spending, sync_service
from budget.recurring import schedule
from budget.spending import MONTHS, MONTHS_GEN, add_months, month_label, month_start, parse_month
from budget.storage import db
from budget.web import charts
from budget.web.common import Panel

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(hours=30)  # synchronizacje są 3×/dobę, więc dłuższa przerwa to sygnał


@dataclass(frozen=True)
class TimelineRow:
    day: date
    event: forecast.Event | None  # None: dno wyznaczył sam Flex, bez zdarzenia w tym dniu
    balance: Decimal | None  # saldo na koniec dnia, tylko w ostatnim wierszu dnia
    low: bool


def forecast_timeline(fc: forecast.Forecast) -> list[TimelineRow]:
    """Zdarzenia prognozy chronologicznie, z saldem po dniu i wyróżnionym dnem."""
    balances = dict(fc.days)
    rows: list[TimelineRow] = []
    for i, e in enumerate(fc.events):
        last = i + 1 == len(fc.events) or fc.events[i + 1].day != e.day
        rows.append(
            TimelineRow(e.day, e, balances[e.day] if last else None, last and e.day == fc.low_day)
        )
    if fc.low_day is not None and all(r.day != fc.low_day for r in rows):
        at = next((i for i, r in enumerate(rows) if r.day > fc.low_day), len(rows))
        rows.insert(at, TimelineRow(fc.low_day, None, fc.low, True))
    return rows


def compare_label(m: spending.Month) -> str:
    """Podpis porównania: „vs 1–5 września” dla niepełnego miesiąca, „vs wrzesień” dla pełnego."""
    first, end = m.prev_window or (m.prev_month, m.month)
    if not m.prev_partial:
        return f"vs {MONTHS[first.month - 1]}"
    last = end - timedelta(days=1)
    days = str(first.day) if first.day == last.day else f"{first.day}–{last.day}"
    return f"vs {days} {MONTHS_GEN[first.month - 1]}"


def router(panel: Panel) -> APIRouter:
    r = APIRouter()

    @r.get("/", response_class=HTMLResponse)
    async def home(request: Request, month: str | None = None, edit: str = "") -> HTMLResponse:
        conn, now = panel.conn, panel.service.now()
        today = now.date()
        start = parse_month(month, today)
        nxt = add_months(start, 1)
        ym = f"{start:%Y-%m}"
        m = spending.build(conn, start, today)
        f = flex.build(panel.service.snapshot, start, today)
        period = f"date_from={start.isoformat()}&date_to={(nxt - timedelta(days=1)).isoformat()}"
        upcoming: list[schedule.Due] = []
        mv = None
        if f.is_current:  # nadchodzące płatności mają sens tylko dla bieżącego miesiąca
            mv = schedule.for_month(panel.service.snapshot, start, today)
            upcoming = sorted(
                (d for d in mv.rows if d.status in (schedule.EXPECTED, schedule.LATE)),
                key=lambda d: d.sort_day,
            )
        fc, buffer = None, Decimal(panel.service.settings.forecast_buffer)
        if mv is not None:  # prognoza (tylko bieżący miesiąc) nie może zablokować strony głównej
            try:
                fc = forecast.build(
                    panel.service.snapshot,
                    today,
                    now,
                    f,
                    mv,
                    buffer,
                    forecast.payday_series_id(conn),
                    forecast.include_card_debt(conn),
                )
            except Exception:
                log.exception("Prognoza do wypłaty nieudana")
        sync_at = sync_service.last_success(conn)
        record = sessions.current(conn)
        return panel.render(
            request,
            "home.html",
            layout=home_layout.load(conn),
            edit=edit == "1",
            f=f,
            m=m,
            ym=ym,
            label=month_label(start),
            prev_label=month_label(m.prev_month),
            next_label=month_label(m.next_month) if m.next_month else "",
            period=period,
            compare=compare_label(m),
            slices=charts.donut_slices(
                m.expense_groups,
                m.uncategorized_out,
                m.uncategorized_out_count,
                period=period,
                other_href=f"/spending?month={ym}",
                review_href=f"/review?month={ym}",
            ),
            bars=charts.month_bars(spending.monthly_totals(conn, today), start),
            mv=mv,
            upcoming=upcoming[:5],
            upcoming_more=max(len(upcoming) - 5, 0),
            recent=spending.recent(conn, start, nxt),
            sync_at=sync_at,
            stale=bool(sync_at and now - datetime.fromisoformat(sync_at) > STALE_AFTER),
            consent_days=record.days_left(now) if record and record.active else None,
            cm=card.month_status(conn, today) if f.is_current else None,
            cd=card.due_status(conn, today) if f.is_current else None,
            fc=fc,
            chart=charts.forecast_line(fc.days, buffer, fc.events, fc.payday) if fc else None,
            timeline=forecast_timeline(fc) if fc else [],
        )

    def layout_response(request: Request) -> Response:
        if request.headers.get("hx-request"):
            return panel.partial(request, "_home_layout.html", layout=home_layout.load(panel.conn))
        return panel.redirect(request, "/?edit=1")

    @r.post("/layout/move")
    async def layout_move(
        request: Request, key: str = Form(...), delta: int = Form(...)
    ) -> Response:
        if key not in home_layout.TILES or delta not in (-1, 1):
            raise HTTPException(400)
        home_layout.move(panel.conn, key, delta)
        return layout_response(request)

    @r.post("/layout/toggle")
    async def layout_toggle(request: Request, key: str = Form(...)) -> Response:
        if key not in home_layout.TILES:
            raise HTTPException(400)
        home_layout.toggle(panel.conn, key)
        return layout_response(request)

    @r.post("/layout/reset")
    async def layout_reset(request: Request) -> Response:
        home_layout.reset(panel.conn)
        return layout_response(request)

    @r.post("/forecast/card-debt")
    async def card_debt(request: Request, include: str = Form("")) -> Response:
        db.kv_set(panel.conn, forecast.CARD_DEBT_KEY, include == "1")
        return panel.redirect(
            request,
            "/",
            "Zadłużenie karty jest odejmowane w prognozie."
            if include == "1"
            else "Zadłużenie karty nie jest odejmowane w prognozie.",
        )

    @r.post("/forecast/payday-date")
    async def payday_date(
        request: Request,
        series: int = Form(...),
        month: str = Form(...),
        day: str = Form(""),
        reset: str = Form(""),
    ) -> Response:
        """Faktyczna data wypłaty w miesiącu terminu (M21 E1); `reset` wraca do dnia z serii."""
        conn, today = panel.conn, panel.service.now().date()
        try:
            start = date.fromisoformat(f"{month}-01")
        except ValueError:
            raise HTTPException(400) from None
        if reset:
            schedule.set_override(conn, series, start, None)
            return panel.redirect(request, "/", "Termin wypłaty wraca do dnia z serii.")
        try:
            when: date | None = date.fromisoformat(day)
        except ValueError:
            when = None
        if when is None or month_start(when) != start or when <= today:
            return panel.redirect(
                request,
                "/",
                f"Podaj datę po dzisiejszej w miesiącu terminu ({MONTHS[start.month - 1]}).",
                "error",
            )
        schedule.set_override(conn, series, start, when)
        return panel.redirect(request, "/", f"Wypłata {when:%d.%m} — prognoza liczy do tej daty.")

    return r
