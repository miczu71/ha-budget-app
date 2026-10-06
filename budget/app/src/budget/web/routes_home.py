"""Strona główna (M13): podsumowanie miesiąca — Zostało, wykresy, bilans, nadchodzące, ostatnie."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from budget import card, flex, sessions, spending, sync_service
from budget.recurring import schedule
from budget.spending import MONTHS, MONTHS_GEN, add_months, month_label, parse_month
from budget.web import charts
from budget.web.common import Panel

STALE_AFTER = timedelta(hours=30)  # synchronizacje są 3×/dobę, więc dłuższa przerwa to sygnał


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
    async def home(request: Request, month: str | None = None) -> HTMLResponse:
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
        sync_at = sync_service.last_success(conn)
        record = sessions.current(conn)
        return panel.render(
            request,
            "home.html",
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
        )

    return r
