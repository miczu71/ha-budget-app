"""Strona główna (M13): podsumowanie miesiąca — Zostało, wykresy, bilans, nadchodzące, ostatnie."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from budget import (
    card,
    flex,
    forecast,
    home_layout,
    networth,
    piggy,
    savings,
    sessions,
    spending,
    stocks,
    sync_service,
)
from budget.money import ZERO
from budget.recurring import schedule
from budget.spending import MONTHS, MONTHS_GEN, add_months, month_label, month_start, parse_month
from budget.storage import db
from budget.timing import timed
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


@dataclass(frozen=True)
class BalanceTiles:
    account: Decimal
    card_debt: Decimal | None  # None: brak karty — kafelek pominięty
    savings: Decimal  # konta oszczędnościowe + skarbonki
    piggy_total: Decimal
    piggies: list[piggy.Status]
    stocks_value: Decimal | None  # None: brak danych o akcjach — kafelek ukryty
    stocks_vest: date | None
    stocks_stale: bool


def _holding(conn: sqlite3.Connection) -> stocks.Holding | None:
    """Akcje to dodatek kafelków: błąd danych nie może zabrać kafelków kont."""
    try:
        return stocks.load(conn)
    except Exception:
        log.exception("Odczyt akcji do kafelka nieudany")
        return None


def balance_tiles(
    panel: Panel,
    fc: forecast.Forecast | None,
    today: date,
    sv: savings.Overview | None,
    has_card: bool,
    holding: stocks.Holding | None,
) -> BalanceTiles | None:
    """Salda nad hero (M31 E4): konto, karta, oszczędności ze skarbonkami; None bez sald."""
    balances = fc.balances if fc else forecast.read_balances(panel.conn)
    if balances is None:
        return None
    piggies = (
        fc.piggies if fc else piggy.statuses(panel.service.snapshot, today, month_start(today))
    )
    in_piggies = sum((s.balance for s in piggies), ZERO)
    return BalanceTiles(
        account=balances.account,
        card_debt=balances.card_debt if has_card else None,
        savings=(sv.total if sv else ZERO) + in_piggies,
        piggy_total=in_piggies,
        piggies=sorted(piggies, key=lambda s: s.piggy.name.lower()),
        stocks_value=holding.market_value if holding else None,
        stocks_vest=holding.next_vest if holding else None,
        stocks_stale=bool(holding)
        and holding.fetched_at.date() < today - timedelta(days=stocks.STALE_DAYS),
    )


def router(panel: Panel) -> APIRouter:
    r = APIRouter()

    @r.get("/", response_class=HTMLResponse)
    async def home(request: Request, month: str | None = None, edit: str = "") -> HTMLResponse:
        conn, now = panel.conn, panel.service.now()
        today = now.date()
        start = parse_month(month, today)
        nxt = add_months(start, 1)
        ym = f"{start:%Y-%m}"
        with timed("h_spending"):
            m = spending.build(conn, start, today)
        with timed("h_flex"):
            f = flex.build(panel.service.snapshot, start, today)
        period = f"date_from={start.isoformat()}&date_to={(nxt - timedelta(days=1)).isoformat()}"
        upcoming: list[schedule.Due] = []
        mv = None
        if f.is_current:  # nadchodzące płatności mają sens tylko dla bieżącego miesiąca
            with timed("h_schedule"):
                mv = schedule.for_month(panel.service.snapshot, start, today)
            upcoming = sorted(
                (d for d in mv.rows if d.status in (schedule.EXPECTED, schedule.LATE)),
                key=lambda d: d.sort_day,
            )
        fc, buffer = None, Decimal(panel.service.settings.forecast_buffer)
        if mv is not None:  # prognoza (tylko bieżący miesiąc) nie może zablokować strony głównej
            try:
                with timed("h_forecast"):
                    fc = forecast.build(
                        panel.service.snapshot,
                        today,
                        now,
                        mv,
                        buffer,
                        forecast.payday_series_id(conn),
                        forecast.include_card_debt(conn),
                    )
            except Exception:
                log.exception("Prognoza do wypłaty nieudana")
        sv = savings.overview(conn, today, 1)
        cm = card.month_status(conn, today) if f.is_current else None
        tiles = None
        if f.is_current:  # kafelki to dodatek: błąd nie może zablokować strony głównej
            try:
                tiles = balance_tiles(panel, fc, today, sv, bool(cm), _holding(conn))
            except Exception:
                log.exception("Kafelki sald nieudane")
        nw = None
        try:  # kafelek majątku to dodatek: błąd nie może zablokować strony głównej
            with timed("h_networth"):
                snap = networth.compute(conn, today, snap=panel.service.snapshot)
                nw = (snap, networth.change(conn, snap.total, today, 30))
        except Exception:
            log.exception("Kafelek majątku nieudany")
        with timed("h_year"):
            yr = panel.service.year_projection()
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
            sv=sv,
            upcoming=upcoming[:5],
            upcoming_more=max(len(upcoming) - 5, 0),
            recent=spending.recent(conn, start, nxt),
            sync_at=sync_at,
            stale=bool(sync_at and now - datetime.fromisoformat(sync_at) > STALE_AFTER),
            consent_days=record.days_left(now) if record and record.active else None,
            cm=cm,
            cd=card.due_status(conn, today) if f.is_current else None,
            fc=fc,
            tiles=tiles,
            nw=nw,
            yr=yr,
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
