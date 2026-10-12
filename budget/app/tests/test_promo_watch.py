"""Monitor edycji promocji Profit (M10 E7): parser, stan, okno badania, push i dzwonek."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from budget import inbox, promo_watch, summary
from budget.snapshot import Snapshot

from .test_categorize_engine import conn
from .test_savings import make

__all__ = ["conn"]

WAW = ZoneInfo("Europe/Warsaw")
# Fragmenty w układzie, w jakim pypdf zwraca regulamin (łamanie linii w środku zdań, nbsp).
REGULATION = """Regulamin promocji
„Nowe środki na Koncie
Oszczędnościowym Profit”,
edycja {n}
Obowiązuje od {start} roku
JAKI JEST CZAS OBOWIĄZYWANIA PROMOCJI
3. Do promocji możesz przystąpić od {start} r. do {deadline} r.
4. Okres promocyjny trwa przez 91 dni od dnia, w którym przystąpisz do promocji.
7. {baseline} roku (dzień badania sald) obliczamy, ile masz pieniędzy:
"""


def text(
    n: int = 77,
    start: str = "11 września 2026",
    deadline: str = "21 października 2026",
    baseline: str = "4 września 2026",
) -> str:
    return REGULATION.format(n=n, start=start, deadline=deadline, baseline=baseline)


def now(day: int, month: int = 10) -> datetime:
    return datetime(2026, month, day, 8, 0, tzinfo=WAW)


async def fetch(c: sqlite3.Connection, body: str, when: datetime) -> None:
    async def get_text() -> str:
        return body

    await promo_watch.refresh(c, when, get_text)


def test_parse_edition() -> None:
    ed = promo_watch.parse(text())
    assert (ed.number, ed.baseline, ed.start, ed.deadline, ed.days) == (
        77,
        date(2026, 9, 4),
        date(2026, 9, 11),
        date(2026, 10, 21),
        91,
    )
    assert ed.window() == (date(2026, 10, 15), date(2026, 10, 21))


def test_parse_reports_what_is_missing() -> None:
    with pytest.raises(promo_watch.WatchError, match="baseline, range"):
        promo_watch.parse("edycja 78\ntrwa przez 91 dni")
    with pytest.raises(promo_watch.WatchError, match="Nieznany miesiąc"):
        promo_watch.parse(text(deadline="21 octobre 2026"))


def tiny_pdf(line: str) -> bytes:
    """Jednostronicowy PDF z jedną linią tekstu (ASCII) i poprawną tablicą xref."""
    stream = f"BT /F1 12 Tf 10 100 Td ({line}) Tj ET".encode()
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length %d>>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (n, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    return out + b"trailer<</Root 1 0 R/Size %d>>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)


def test_pdf_text_reads_a_pdf() -> None:
    assert "edycja 78" in promo_watch.pdf_text(tiny_pdf("edycja 78"))


async def test_refresh_first_read_is_silent_and_new_edition_is_pending(
    conn: sqlite3.Connection,
) -> None:
    assert promo_watch.load(conn) is None
    await fetch(conn, text(), now(12))
    w = promo_watch.load(conn)
    assert w and w.edition and w.edition.number == 77 and w.pending_confirm is None and not w.error
    await fetch(conn, text(), now(13))  # ta sama edycja — nic nowego
    assert promo_watch.load(conn).pending_confirm is None  # type: ignore[union-attr]
    await fetch(
        conn, text(78, "22 października 2026", "3 grudnia 2026", "16 października 2026"), now(22)
    )
    w = promo_watch.load(conn)
    assert w and w.edition and w.edition.number == 78 and w.pending_confirm == 78


async def test_refresh_error_is_kept_then_cleared(conn: sqlite3.Connection) -> None:
    await fetch(conn, text(), now(12))
    await fetch(conn, "zmieniony układ", now(13))
    w = promo_watch.load(conn)
    assert w and w.error and "WatchError" in w.error and w.edition and w.edition.number == 77
    assert w.error_since == now(13)
    await fetch(conn, "nadal źle", now(14))
    assert promo_watch.load(conn).error_since == now(13)  # type: ignore[union-attr]
    await fetch(conn, text(), now(15))
    w = promo_watch.load(conn)
    assert w and w.error is None and w.error_since is None


async def test_refresh_swallows_fetch_errors(conn: sqlite3.Connection) -> None:
    async def boom() -> str:
        raise httpx.ConnectError("brak sieci")

    await promo_watch.refresh(conn, now(12), boom)
    w = promo_watch.load(conn)
    assert w and w.edition is None and "ConnectError" in (w.error or "")


async def watched(c: sqlite3.Connection, **kw: str) -> promo_watch.Watch:
    await fetch(c, text(**kw), now(1))
    w = promo_watch.load(c)
    assert w
    return w


async def test_push_before_window(conn: sqlite3.Connection) -> None:
    w = await watched(conn)  # okno 15–21.10
    kinds = {
        d: [m.kind for m in summary.promo_messages(w, date(2026, 10, d))]
        for d in (11, 12, 14, 15, 16)
    }
    assert kinds == {
        11: [],
        12: ["promo_window"],
        14: ["promo_window"],
        15: ["promo_window"],
        16: [],
    }
    msg = summary.promo_messages(w, date(2026, 10, 12))[0]
    assert "między 15.10 a 21.10" in msg.text and "przed 15.10" in msg.text
    assert msg.period == "77-3"


async def test_push_confirms_new_edition_once(conn: sqlite3.Connection) -> None:
    await fetch(conn, text(), now(12))
    await fetch(
        conn, text(78, "22 października 2026", "3 grudnia 2026", "16 października 2026"), now(22)
    )
    w = promo_watch.load(conn)
    assert w
    msgs = [m for m in summary.promo_messages(w, date(2026, 10, 22)) if m.kind == "promo_confirm"]
    assert len(msgs) == 1 and "16.10" in msgs[0].text and "03.12" in msgs[0].text


async def test_due_sends_window_push_and_marks_sent(conn: sqlite3.Connection) -> None:
    make(conn)
    await fetch(conn, text(), now(12))
    snap = Snapshot(conn)
    first = [m for m in summary.due(snap, now(12)) if m.kind == "promo_window"]
    assert len(first) == 1
    summary.mark_sent(conn, first[0])
    assert not [m for m in summary.due(snap, now(12)) if m.kind == "promo_window"]


async def test_bell_cards(conn: sqlite3.Connection) -> None:
    w = await watched(conn)
    memo = inbox.BalanceMemo()

    def cards(day: int, month: int = 10) -> dict[str, str]:
        out = inbox.promo_cards(conn, inbox.Context(now(day, month), Snapshot(conn)), memo)
        return {i.kind: i.severity for i in out}

    assert cards(1) == {"promo_intake": "info"}  # do początku okna > 10 dni; badanie minęło
    assert cards(6) == {"promo_intake": "info", "promo_window": "info"}  # 9 dni do okna
    assert cards(12)["promo_window"] == "warn"  # 3 dni do okna
    assert cards(22) == {"promo_wait": "info"}  # po 21.10 bez nowej edycji
    assert w.edition


async def test_bell_error_card_after_three_days(conn: sqlite3.Connection) -> None:
    await fetch(conn, "zły układ", now(1))
    memo = inbox.BalanceMemo()

    def kinds(day: int) -> list[str]:
        return [
            i.kind for i in inbox.promo_cards(conn, inbox.Context(now(day), Snapshot(conn)), memo)
        ]

    assert kinds(2) == []
    assert kinds(4) == ["promo_error"]
