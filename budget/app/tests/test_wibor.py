"""Notowania WIBOR 3M: parser, dzień ustalenia stawki, odczyt i stan (M9 E4a)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

import pytest

from budget import inbox, wibor
from budget.snapshot import Snapshot

from .test_categorize_engine import conn

__all__ = ["conn"]

PAGE = (
    '<tr><td>Data</td>\n<td class="textBold">2026-09-04</td></tr>\n'
    '<tr><td><a href="wibor?rateDate=&rateChartType=1m">WIBOR 1M</a></td>'
    '<td class="textBold change down"> 3,77% (-0,0300) </td></tr>\n'
    '<tr><td><a href="wibor?rateDate=&rateChartType=3m">WIBOR 3M</a></td>\n'
    '  <td class="textBold change down">\n      3,80%\n      (-0,0100)\n  </td></tr>'
)
NOW = datetime(2026, 10, 12, 7, 0)


def test_parse_reads_3m_row_and_rejects_changed_layout() -> None:
    assert wibor.parse(PAGE) == (date(2026, 9, 4), Decimal("3.80"))
    with pytest.raises(wibor.WibError):
        wibor.parse("<html>zmieniony układ</html>")


def test_fixing_day_skips_weekends() -> None:
    assert wibor.fixing_day(date(2026, 9, 9)) == date(2026, 9, 4)  # śr → pt (3 dni robocze)
    assert wibor.fixing_day(date(2026, 12, 9)) == date(2026, 12, 4)
    assert wibor.fixing_day(date(2026, 12, 7)) == date(2026, 12, 2)  # pn → śr


def feed(table: dict[date | None, tuple[date, str]]) -> wibor.Fetch:
    async def get(day: date | None) -> tuple[date, Decimal]:
        found, value = table[day]
        return found, Decimal(value)

    return get


async def test_refresh_stores_latest_and_backfills_fixing_day(conn: sqlite3.Connection) -> None:
    get = feed({None: (date(2026, 10, 9), "3.88"), date(2026, 9, 4): (date(2026, 9, 4), "3.80")})
    await wibor.refresh(conn, NOW, [date(2026, 9, 4)], get)
    assert wibor.quotes(conn) == {
        date(2026, 9, 4): Decimal("3.80"),
        date(2026, 10, 9): Decimal("3.88"),
    }
    assert wibor.at(conn, date(2026, 9, 9)) == (date(2026, 9, 4), Decimal("3.80"))
    assert wibor.at(conn, date(2026, 9, 3)) is None
    assert wibor.error(conn) is None


async def test_refresh_does_not_refetch_covered_day(conn: sqlite3.Connection) -> None:
    get = feed({None: (date(2026, 10, 9), "3.88"), date(2026, 10, 7): (date(2026, 10, 6), "3.85")})
    await wibor.refresh(conn, NOW, [date(2026, 10, 7)], get)  # 7.10 → notowanie z 6.10
    await wibor.refresh(conn, NOW, [date(2026, 10, 7)], feed({None: (date(2026, 10, 9), "3.88")}))
    assert wibor.error(conn) is None  # drugi odczyt nie pytał o 7.10 (brak w `feed` = błąd)
    assert wibor.at(conn, date(2026, 10, 7)) == (date(2026, 10, 6), Decimal("3.85"))


async def test_refresh_swallows_errors_keeps_quotes_and_clears_on_success(
    conn: sqlite3.Connection,
) -> None:
    await wibor.refresh(conn, NOW, (), feed({None: (date(2026, 10, 9), "3.88")}))

    async def boom(day: date | None) -> tuple[date, Decimal]:
        raise wibor.WibError("zmiana układu")

    await wibor.refresh(conn, datetime(2026, 10, 13, 7), (), boom)
    await wibor.refresh(conn, datetime(2026, 10, 14, 7), (), boom)
    err = wibor.error(conn)
    assert err is not None and "zmiana układu" in err[0] and err[1] == datetime(2026, 10, 13, 7)
    assert wibor.at(conn, date(2026, 10, 12)) == (date(2026, 10, 9), Decimal("3.88"))
    await wibor.refresh(
        conn, datetime(2026, 10, 15, 7), (), feed({None: (date(2026, 10, 9), "3.88")})
    )
    assert wibor.error(conn) is None


async def test_error_card_appears_after_alert_days_only(conn: sqlite3.Connection) -> None:
    async def boom(day: date | None) -> tuple[date, Decimal]:
        raise wibor.WibError("zmiana układu")

    await wibor.refresh(conn, datetime(2026, 10, 10, 7), (), boom)

    def cards(day: int) -> list[inbox.Item]:
        ctx = inbox.Context(datetime(2026, 10, day, 7), Snapshot(conn))
        return inbox.wibor_error(conn, ctx, inbox.BalanceMemo())

    assert cards(12) == []
    assert [c.kind for c in cards(13)] == ["wibor_error"] and "10.10" in cards(13)[0].detail
