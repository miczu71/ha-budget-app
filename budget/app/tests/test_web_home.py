"""Panel M13: strona główna (podsumowanie budżetu), nawigacja z menu, Status pod `/status`."""

from __future__ import annotations

import dataclasses
import sqlite3
from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest

from budget import forecast, spending
from budget.categorize.rules import Conditions, TextCondition
from budget.recurring import schedule as sch
from budget.recurring import series as S
from budget.service import Service
from budget.storage.db import now_iso
from budget.web.common import fmt_money
from budget.web.routes_home import compare_label, forecast_timeline

from .test_recurring_schedule import make_event
from .test_web import INGRESS, _client
from .test_web_categorize import DAY, _seed

__all__ = ["service"]
from .test_web import service

MONTH = DAY[:7]


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


async def test_home_without_budget_invites_to_set_it(client: httpx.AsyncClient) -> None:
    page = (await client.get("/")).text
    assert "Podsumowanie" in page and "Ustaw budżet" in page
    assert f'href="{INGRESS}/budget"' in page and "Nic nie czeka na decyzję" in page


async def test_home_shows_flex_remaining(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)  # elastyczne: 280
    await client.post("/budget/amount", data={"month": MONTH, "amount": "1000"})
    page = (await client.get("/")).text
    assert "Zostało na elastyczne" in page and "720,00" in page
    assert "Na dzień do końca miesiąca" in page and 'class="mark"' in page


async def test_status_is_last_in_the_menu_not_in_the_bar(client: httpx.AsyncClient) -> None:
    page = (await client.get("/")).text
    bar, menu = page.split('class="more-panel"')
    assert f"{INGRESS}/status" not in bar and f"{INGRESS}/rules" not in bar
    order = [menu.index(f'href="{INGRESS}/{p}"') for p in ("review", "rules", "bank", "status")]
    assert order == sorted(order)


async def test_status_page_moved_to_status(client: httpx.AsyncClient) -> None:
    r = await client.get("/status")
    assert r.status_code == 200 and "<h1>Status</h1>" in r.text
    assert 'class="more on"' in r.text  # aktywna strona podświetla menu


async def test_fonts_are_served_immutable(client: httpx.AsyncClient) -> None:
    for name in ("InterVariable.woff2", "SourceSerif4-latin.woff2"):
        r = await client.get(f"/static/fonts/{name}")
        assert r.status_code == 200 and "immutable" in r.headers["cache-control"]


async def test_donut_slices_legend_and_links(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)  # Jedzenie 80 (id 2), Transport 200 (id 4), pensja bez kategorii
    page = (await client.get("/")).text
    assert page.count('class="slice c') == 2 and "Gdzie poszły pieniądze" in page
    assert "<title>Transport: 200,00\xa0zł (71%)</title>" in page
    assert "<title>Jedzenie: 80,00\xa0zł (29%)</title>" in page
    assert page.index('class="legend-name">Transport') < page.index('class="legend-name">Jedzenie')
    assert f'href="{INGRESS}/transactions?category=4&amp;date_from={DAY}&amp;date_to=' in page
    assert '<span class="donut-total">280,00' in page  # środek: suma wydatków miesiąca


async def test_uncategorized_slice_links_to_review(
    client: httpx.AsyncClient, service: Service
) -> None:
    _seed(service.conn)
    from .test_categorize_engine import add

    add(service.conn, "-40.00", "card", "SKLEP ABC XYZ", day=DAY)  # bez kategorii
    page = (await client.get("/")).text
    assert "<title>Bez kategorii: 40,00\xa0zł" in page
    assert f'href="{INGRESS}/review?month={MONTH}"' in page


async def test_empty_month_has_no_donut_and_no_upcoming(client: httpx.AsyncClient) -> None:
    page = (await client.get("/?month=2020-01")).text
    assert "<h1>Styczeń 2020</h1>" in page
    assert "Brak wydatków w tym miesiącu." in page and 'class="slice' not in page
    assert "Za mało danych" in page and "Co jeszcze zejdzie" not in page
    assert f'href="{INGRESS}/?month=2020-02"' in page  # strzałka do następnego miesiąca


async def test_month_switch_and_current_month_has_no_next(
    client: httpx.AsyncClient, service: Service
) -> None:
    _seed(service.conn)
    page = (await client.get("/")).text
    first = date.today().replace(day=1)
    prev = (first - timedelta(days=1)).replace(day=1)
    assert f'href="{INGRESS}/?month={prev:%Y-%m}"' in page
    assert f"?month={(first + timedelta(days=32)):%Y-%m}" not in page  # brak przyszłości
    older = (await client.get(f"/?month={prev:%Y-%m}")).text
    assert f"<h1>{spending.month_label(prev).capitalize()}</h1>" in older
    assert f'href="{INGRESS}/?month={MONTH}"' in older  # następny = bieżący


def test_compare_label_partial_and_full_period() -> None:
    def month(prev_from: date, prev_to: date) -> spending.Month:
        return spending.Month(
            month=date(2026, 9, 1),
            prev_month=date(2026, 8, 1),
            next_month=None,
            prev_window=(prev_from, prev_to),
        )

    assert compare_label(month(date(2026, 8, 1), date(2026, 8, 6))) == "vs 1–5 sierpnia"
    assert compare_label(month(date(2026, 8, 1), date(2026, 8, 2))) == "vs 1 sierpnia"
    assert compare_label(month(date(2026, 8, 1), date(2026, 9, 1))) == "vs sierpień"


async def test_balance_tiles_show_totals_and_change(
    client: httpx.AsyncClient, service: Service
) -> None:
    _seed(service.conn)
    page = (await client.get("/")).text
    assert "Bilans miesiąca" in page
    assert '<span class="stat-label">Wydatki</span><span class="stat-value">280,00' in page
    assert '<span class="stat-label">Wpływy</span><span class="stat-value">5' in page  # 5 000,00
    assert "nowe" in page  # poprzedni okres bez danych


async def test_upcoming_payments_card(client: httpx.AsyncClient, service: Service) -> None:
    assert "Co jeszcze zejdzie" not in (await client.get("/")).text  # brak serii
    S.insert(
        service.conn,
        name="Abonament Q",
        direction="out",
        cadence="M",
        conditions=Conditions(text=(TextCondition("counterparty_name", "equals", "Q"),)),
        expected=Decimal("43.00"),
        tolerance=Decimal("5"),
        anchor_day=date.today().day,  # termin dziś = oczekiwana
        status="active",
        origin="manual",
        key=None,
    )
    page = (await client.get("/")).text
    assert "Co jeszcze zejdzie" in page and "Abonament Q" in page and "43,00" in page
    assert f'href="{INGRESS}/recurring"' in page
    prev = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    assert "Co jeszcze zejdzie" not in (await client.get(f"/?month={prev}")).text  # tylko bieżący


async def test_recent_transactions_skip_internal_transfers(
    client: httpx.AsyncClient, service: Service
) -> None:
    _seed(service.conn)
    page = (await client.get("/")).text
    assert "Ostatnie transakcje" in page and "−200,00" in page and "5\u202f000,00" in page
    assert "700,00" not in page  # spłata karty (przelew wewnętrzny) nie wchodzi
    assert f'href="{INGRESS}/transactions?date_from={DAY}&amp;date_to=' in page


async def test_freshness_line(client: httpx.AsyncClient, service: Service) -> None:
    assert "Brak synchronizacji z bankiem" in (await client.get("/")).text
    old = (service.now() - timedelta(days=3)).isoformat()
    _sync(service.conn, old, "ok")
    page = (await client.get("/")).text
    assert "Dane z " in page and "nieświeże" in page
    _sync(service.conn, now_iso(), "partial")
    page = (await client.get("/")).text
    assert "Dane z " in page and "nieświeże" not in page


def _sync(conn: sqlite3.Connection, finished: str, status: str) -> None:
    conn.execute(
        "INSERT INTO sync_log (trigger, started_at, finished_at, status) "
        "VALUES ('schedule', ?, ?, ?)",
        (finished, finished, status),
    )


async def test_charts_render_and_there_is_no_theme_switch(
    client: httpx.AsyncClient, service: Service
) -> None:
    _seed(service.conn)
    page = (await client.get("/")).text
    assert 'class="slice c' in page and 'class="bars"' in page
    assert "data-theme" not in page and 'content="#efecea"' in page  # jeden wygląd (Monarch)
    assert "Wygląd" not in page and "/theme" not in page
    assert (await client.post("/theme", data={"theme": "neon"})).status_code in (404, 405)


# --- „Do wypłaty” (M8 E1) ----------------------------------------------------------------


def _balances(conn: sqlite3.Connection, account: str = "9136.98", debt: str = "377.67") -> None:
    conn.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', ?)",
        (now_iso(),),
    )
    conn.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (2, 'card', 'PLN', ?)",
        (now_iso(),),
    )
    at = now_iso()
    for acc, kind, amount in ((1, "ITAV", account), (2, "ITBD", debt)):
        conn.execute(
            "INSERT INTO balance_snapshot (account_id, balance_type, amount, currency, fetched_at)"
            " VALUES (?, ?, ?, 'PLN', ?)",
            (acc, kind, amount, at),
        )


async def test_home_shows_forecast_with_card_debt_row(
    client: httpx.AsyncClient, service: Service
) -> None:
    _balances(service.conn)
    page = (await client.get("/")).text
    assert "Do końca miesiąca" in page and "Starczy · zapas" in page
    for text in ("Rachunek", "karta", "Wolne dziś", "Flex"):
        assert text in page
    for amount in ("9136.98", "377.67", "8759.31"):
        assert fmt_money(amount, "PLN") in page
    assert "poniżej" not in page and "dziennie" in page
    assert 'role="switch"' in page and 'name="include"' in page and "checked" in page


async def test_forecast_card_row_is_visible_without_debt(
    client: httpx.AsyncClient, service: Service
) -> None:
    _balances(service.conn, debt="0.00")
    page = (await client.get("/")).text
    assert "karta " + fmt_money("0.00", "PLN") in page


async def test_forecast_flags_lowest_point_below_buffer(
    client: httpx.AsyncClient, service: Service
) -> None:
    _balances(service.conn)
    service.settings = service.settings.model_copy(update={"forecast_buffer": 10_000})
    page = (await client.get("/")).text
    assert "Poniżej bufora o" in page and "poniżej bufora (" in page
    assert fmt_money("10000", "PLN") in page and "Starczy" not in page


@pytest.mark.parametrize(
    ("low", "safe", "expected"),
    [
        (
            "-150.00",
            "190.00",
            ("Zabraknie", fmt_money("150.00", "PLN"), "Wydawaj do", fmt_money("190.00", "PLN")),
        ),
        ("-150.00", "-20.00", ("Zabraknie", "Same płatności cykliczne przekraczają")),
        ("-150.00", None, ("Zabraknie",)),
    ],
)
async def test_forecast_verdict_when_short(
    client: httpx.AsyncClient,
    service: Service,
    monkeypatch: pytest.MonkeyPatch,
    low: str,
    safe: str | None,
    expected: tuple[str, ...],
) -> None:
    _balances(service.conn)
    real = forecast.build

    def short(*args: object, **kwargs: object) -> forecast.Forecast | None:
        fc = real(*args, **kwargs)  # type: ignore[arg-type]
        assert fc is not None
        return dataclasses.replace(
            fc, low=Decimal(low), safe_per_day=None if safe is None else Decimal(safe)
        )

    monkeypatch.setattr(forecast, "build", short)
    page = (await client.get("/")).text
    for text in expected:
        assert text in page
    assert "Starczy" not in page
    assert ("Wydawaj do" in page) is (safe is not None and Decimal(safe) > 0)


def _days(*balances: str) -> list[tuple[date, Decimal]]:
    return [(date(2026, 10, 4 + i), Decimal(b)) for i, b in enumerate(balances)]


def test_forecast_timeline_shows_balance_once_per_day_and_marks_the_low_day() -> None:
    fc = forecast.Forecast(
        payday=None,
        payday_series=None,
        horizon_end=date(2026, 10, 6),
        days=_days("900", "780", "1080"),
        events=[make_event(7, 5, "-100"), make_event(8, 5, "-20"), make_event(9, 6, "300")],
        low=Decimal(780),
        low_day=date(2026, 10, 5),
    )
    rows = forecast_timeline(fc)
    assert [(r.event.due.series.id if r.event else None, r.balance, r.low) for r in rows] == [
        (7, None, False),
        (8, Decimal(780), True),
        (9, Decimal(1080), False),
    ]


def test_forecast_timeline_adds_a_row_when_flex_alone_makes_the_low() -> None:
    fc = forecast.Forecast(
        payday=None,
        payday_series=None,
        horizon_end=date(2026, 10, 6),
        days=_days("900", "700", "650"),
        events=[make_event(7, 4, "-100"), make_event(9, 6, "300")],
        low=Decimal(650),
        low_day=date(2026, 10, 6),
    )
    rows = forecast_timeline(fc)
    assert [(r.day.day, r.event is None, r.low) for r in rows] == [
        (4, False, False),
        (6, False, True),  # zdarzenie w dniu dna: bez dodatkowego wiersza
    ]
    fc = dataclasses.replace(
        fc,
        days=_days("900", "700", "650", "600", "950"),
        events=[make_event(7, 4, "-100"), make_event(9, 8, "300")],
        low_day=date(2026, 10, 5),
    )
    assert [(r.day.day, r.event is None, r.low) for r in forecast_timeline(fc)] == [
        (4, False, False),
        (5, True, True),
        (8, False, False),
    ]


async def _page_with(
    client: httpx.AsyncClient,
    service: Service,
    monkeypatch: pytest.MonkeyPatch,
    **changes: object,
) -> str:
    _balances(service.conn)
    real = forecast.build

    def patched(*args: object, **kwargs: object) -> forecast.Forecast | None:
        fc = real(*args, **kwargs)  # type: ignore[arg-type]
        assert fc is not None
        return dataclasses.replace(fc, **changes)  # type: ignore[arg-type]

    monkeypatch.setattr(forecast, "build", patched)
    return (await client.get("/")).text


async def test_forecast_shows_one_chronological_list_with_links_and_low_row(
    client: httpx.AsyncClient, service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = await _page_with(
        client,
        service,
        monkeypatch,
        days=_days("900", "780", "1080"),
        events=[
            make_event(7, 5, "-100", sch.LATE),
            make_event(8, 5, "-20"),
            make_event(9, 6, "300"),
        ],
        low=Decimal(780),
        low_day=date(2026, 10, 5),
    )
    assert 'class="fc-more"' not in page and "serie do wypłaty" not in page
    assert page.count('class="rows fc-list"') == 1 and "fc-rest" not in page
    assert f'href="{INGRESS}/recurring/7"' in page and f'href="{INGRESS}/recurring/9"' in page
    assert page.count('class="fc-low-row"') == 1 and "spóźniona" in page
    assert page.count('class="row-bal') == 2  # raz na dzień ze zdarzeniami
    assert 'class="fc-zone"' not in page and page.count("fc-mark-") >= 3


@pytest.mark.parametrize(
    ("low_day", "fold"),
    [(5, '<details class="fc-rest">'), (9, '<details class="fc-rest" open>')],
)
async def test_forecast_list_folds_rows_past_eight_and_opens_for_the_low_row(
    client: httpx.AsyncClient,
    service: Service,
    monkeypatch: pytest.MonkeyPatch,
    low_day: int,
    fold: str,
) -> None:
    events = [make_event(i, 4 + i // 2, "-10") for i in range(1, 11)]
    page = await _page_with(
        client,
        service,
        monkeypatch,
        days=_days(*["900"] * 8),
        events=events,
        low_day=date(2026, 10, low_day),
    )
    assert page.count('class="rows fc-list"') == 2 and "pozostałe (2)" in page
    assert fold in page  # dno poza zwiniętą częścią: zwinięte; w niej: otwarte


async def test_forecast_hidden_without_balances_and_in_past_months(
    client: httpx.AsyncClient, service: Service
) -> None:
    assert "Wolne dziś" not in (await client.get("/")).text
    _balances(service.conn)
    prev = spending.add_months(date.today().replace(day=1), -1)
    assert "Wolne dziś" not in (await client.get(f"/?month={prev:%Y-%m}")).text


async def test_forecast_failure_does_not_break_home(
    client: httpx.AsyncClient, service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    _balances(service.conn)

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(forecast, "build", boom)
    resp = await client.get("/")
    assert resp.status_code == 200 and "Zadłużenie karty" not in resp.text


async def test_card_debt_checkbox_is_remembered(
    client: httpx.AsyncClient, service: Service
) -> None:
    _balances(service.conn)
    page = (await client.get("/")).text
    assert 'name="include" value="1" checked' in page and "nie odjęta" not in page
    resp = await client.post("/forecast/card-debt", data={})  # odznaczony checkbox nic nie wysyła
    assert resp.status_code == 303 and not forecast.include_card_debt(service.conn)
    page = (await client.get("/")).text
    assert "nie odjęta" in page and 'name="include" value="1" checked' not in page
    assert fmt_money("9136.98", "PLN") in page  # wolne środki bez odjęcia karty
    await client.post("/forecast/card-debt", data={"include": "1"})
    assert forecast.include_card_debt(service.conn)


async def test_bell_and_service_report_forecast_shortfall(
    client: httpx.AsyncClient, service: Service
) -> None:
    _balances(service.conn)
    assert service.forecast() is not None
    assert "forecast_low" not in [i.kind for i in service.inbox()]
    service.settings = service.settings.model_copy(update={"forecast_buffer": 1_000_000})
    assert "forecast_low" in [i.kind for i in service.inbox()]
    assert "Prognoza: wolne środki poniżej bufora" in (await client.get("/inbox")).text


async def test_service_forecast_is_none_without_balances(service: Service) -> None:
    assert service.forecast() is None and service.inbox() == []


def _order(page: str, *titles: str) -> list[str]:
    return sorted(titles, key=page.index)


async def test_layout_order_and_hidden_tiles_apply_to_home(client: httpx.AsyncClient) -> None:
    page = (await client.get("/")).text
    assert _order(page, "Ostatnie transakcje", "Bilans miesiąca") == [
        "Bilans miesiąca",
        "Ostatnie transakcje",
    ]
    for _ in range(3):  # z pozycji 6 przed „Bilans” (3)
        await client.post("/layout/move", data={"key": "recent", "delta": "-1"})
    await client.post("/layout/toggle", data={"key": "inbox"})
    page = (await client.get("/")).text
    assert _order(page, "Ostatnie transakcje", "Bilans miesiąca") == [
        "Ostatnie transakcje",
        "Bilans miesiąca",
    ]
    assert "Nic nie czeka na decyzję" not in page and "Edytuj układ" in page


async def test_layout_edit_mode_lists_tiles_and_posts_redirect_without_htmx(
    client: httpx.AsyncClient,
) -> None:
    page = (await client.get("/?edit=1")).text
    assert 'id="layout"' in page and "Przywróć domyślny" in page and "home-grid" not in page
    r = await client.post("/layout/toggle", data={"key": "card"})
    assert r.status_code == 303 and r.headers["location"] == f"{INGRESS}/?edit=1"
    assert "(ukryty)" in (await client.get("/?edit=1")).text


async def test_layout_htmx_returns_partial_and_reset_restores(client: httpx.AsyncClient) -> None:
    r = await client.post("/layout/toggle", data={"key": "months"}, headers={"hx-request": "true"})
    assert r.status_code == 200 and r.text.lstrip().startswith("<section") and "(ukryty)" in r.text
    r = await client.post("/layout/reset", headers={"hx-request": "true"})
    assert "(ukryty)" not in r.text


async def test_layout_rejects_unknown_key_and_bad_delta(client: httpx.AsyncClient) -> None:
    assert (await client.post("/layout/toggle", data={"key": "nope"})).status_code == 400
    assert (
        await client.post("/layout/move", data={"key": "recent", "delta": "5"})
    ).status_code == 400
