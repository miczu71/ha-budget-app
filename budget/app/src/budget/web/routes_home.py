"""Strona główna (M13): podsumowanie miesiąca — Zostało, wykresy, bilans, nadchodzące, ostatnie."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

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
from budget.spending import (
    MONTHS,
    MONTHS_GEN,
    add_months,
    month_label,
    month_locative,
    month_start,
    parse_month,
)
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
    )


def payday_start(panel: Panel, today: date) -> date | None:
    """Dzień ostatniej wypłaty z prognozy; None bez prognozy (błąd nie blokuje karty)."""
    now = panel.service.now()
    try:
        mv = schedule.for_month(panel.service.snapshot, month_start(today), today)
        fc = forecast.build(
            panel.service.snapshot,
            today,
            now,
            mv,
            Decimal(panel.service.settings.forecast_buffer),
            forecast.payday_series_id(panel.conn),
            forecast.include_card_debt(panel.conn),
        )
    except Exception:
        log.exception("Początek okresu od wypłaty nieustalony")
        return None
    return fc.period_start if fc else None


def _id(value: str) -> int | None:
    """Id kategorii z zapytania; wszystko, co nie jest liczbą (też puste, „²”, 5000 cyfr) → None."""
    try:
        return int(value) if value.isascii() and value.isdigit() else None
    except ValueError:  # ciąg cyfr dłuższy niż limit konwersji Pythona
        return None


def spending_card(
    panel: Panel,
    start: date,
    today: date,
    since_payday: bool,
    since_date: date | None,
    cat: int | None = None,
    sub: int | None = None,
) -> dict[str, Any]:
    """Kontekst karty wykresu wydatków; `since_date` = dzień ostatniej wypłaty z prognozy
    (tylko bieżący miesiąc), początek okresu „od ostatniej wypłaty”.

    Drill-down (E4): `cat` = kategoria główna (poziom 2), `sub` = podkategoria (poziom 3);
    nieznane albo nieprawidłowe id schodzi o poziom wyżej (1 = jak dotąd)."""
    conn = panel.conn
    since_on = since_payday and since_date is not None
    m = spending.build(conn, start, today, since_date if since_on else None)
    ym = f"{start:%Y-%m}"
    if since_on and since_date is not None:
        days = (today - since_date).days + 1
        period = f"date_from={since_date.isoformat()}&date_to={today.isoformat()}"
        title = f"od {since_date.day} {MONTHS_GEN[since_date.month - 1]}"
        compare = f"vs {days} dni wcześniej"
    else:
        last = add_months(start, 1) - timedelta(days=1)
        period = f"date_from={start.isoformat()}&date_to={last.isoformat()}"
        title = f"w {month_locative(start)}"
        compare = compare_label(m)
    spend_q = f"month={ym}" + ("&since_payday=1" if since_on else "")
    ctx: dict[str, Any] = {
        "sm": m,
        "spend_title": title,
        "spend_compare": compare,
        "since_date": since_date,
        "since_on": since_on,
        "spend_q": spend_q,
        "crumbs": [],
        "back_q": None,
        "drill_level": 1,
        "drill_total": ZERO,
        "drill_share": 0,
        "see_href": None,
        "slices": charts.donut_slices(
            m.expense_groups,
            m.uncategorized_out,
            m.uncategorized_out_count,
            period=period,
            other_href=f"/spending?month={ym}",
            review_href=f"/review?month={ym}",
        ),
    }
    if cat is None:
        return ctx
    g = next((x for x in m.expense_groups if x.category.id == cat), None)
    if g is None:
        return ctx
    cat_q = f"{spend_q}&cat={cat}"
    cat_see = f"/transactions?category={cat}&{period}"
    ctx.update(
        drill_level=2,
        drill_total=g.amount,
        drill_share=round(g.share * 100),
        see_href=cat_see,
        back_q=spend_q,
        crumbs=[("Wszystkie", spend_q), (g.category.name, cat_q)],
    )
    leaf = next((c for c in g.children if sub is not None and c.category.id == sub), None)
    if leaf is None:
        ctx["slices"] = charts.drill_slices(
            [
                charts.Item(
                    key=f"cat-{c.category.id}",
                    label=c.category.name,
                    amount=c.amount,
                    count=c.count,
                    href=f"/transactions?category={c.category.id}&{period}",
                    drill=f"cat={cat}&sub={c.category.id}",
                )
                for c in g.children
            ],
            other_href=cat_see,
        )
        return ctx
    sub_see = f"/transactions?category={leaf.category.id}&{period}"
    window = (
        (since_date, today + timedelta(days=1))
        if since_on and since_date
        else (start, add_months(start, 1))
    )
    purch = spending.purchases(conn, leaf.category.id, *window)
    ctx.update(
        drill_level=3,
        drill_total=sum((p.amount for p in purch), ZERO),  # jak wycinki: zakupy bez zwrotów
        see_href=sub_see,
        back_q=cat_q,
        crumbs=[*ctx["crumbs"], (leaf.category.name, None)],
        slices=charts.drill_slices(
            [
                charts.Item(
                    key=f"txn-{p.id}",
                    label=p.label,
                    amount=p.amount,
                    count=1,
                    href=sub_see,
                )
                for p in purch
            ],
            other_href=sub_see,
        ),
    )
    return ctx


def router(panel: Panel) -> APIRouter:
    r = APIRouter()

    @r.get("/home/spending", response_class=HTMLResponse)
    async def home_spending(
        request: Request,
        month: str | None = None,
        since_payday: str = "",
        cat: str = "",
        sub: str = "",
    ) -> HTMLResponse:
        today = panel.service.now().date()
        start = parse_month(month, today)
        since_date = None
        if start == month_start(today):  # okres od wypłaty to część prognozy (też auto-wykrytej)
            since_date = payday_start(panel, today)
        ctx = spending_card(
            panel, start, today, since_payday == "1", since_date, _id(cat), _id(sub)
        )
        return panel.render(request, "_spending.html", ym=f"{start:%Y-%m}", **ctx)

    @r.get("/", response_class=HTMLResponse)
    async def home(
        request: Request,
        month: str | None = None,
        edit: str = "",
        since_payday: str = "",
        cat: str = "",
        sub: str = "",
    ) -> HTMLResponse:
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
            **spending_card(
                panel,
                start,
                today,
                since_payday == "1",
                fc.period_start if fc else None,
                _id(cat),
                _id(sub),
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
