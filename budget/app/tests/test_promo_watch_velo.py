"""Monitor regulaminu Velobanku (M32 E3): parser, walidacja, stan, karty w dzwonku."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from budget import inbox, promo_watch, promo_watch_velo
from budget.snapshot import Snapshot

from .test_categorize_engine import conn

__all__ = ["conn"]

WAW = ZoneInfo("Europe/Warsaw")
PAGE = (Path(__file__).parent / "fixtures" / "velobank_ror_oferta_2026_12.html").read_text("utf8")
TODAY = date(2026, 10, 22)


def now(day: int, month: int = 10) -> datetime:
    return datetime(2026, month, day, 8, 0, tzinfo=WAW)


def parsed(page: str = PAGE, today: date = TODAY) -> promo_watch_velo.Offer:
    return promo_watch_velo.parse(promo_watch_velo.html_text(page), today)


async def fetch(c: sqlite3.Connection, body: str, when: datetime) -> None:
    async def get_page() -> str:
        return body

    await promo_watch_velo.refresh(c, when, get_page)


def cards(c: sqlite3.Connection, when: datetime) -> list[inbox.Item]:
    memo = inbox.BalanceMemo()
    return inbox.velo_promo_cards(c, inbox.Context(when, Snapshot(c)), memo)


def test_html_text_skips_scripts_and_styles() -> None:
    text = promo_watch_velo.html_text(PAGE)
    assert "edycja 12/2026" in text and "99/1999" not in text and "color:red" not in text


def test_parse_edition_12_2026() -> None:
    o = parsed()
    assert o.label == "12/2026"
    assert (o.promo_rate, o.base_rate) == (4.5, 1.0)
    assert o.min_transactions == 5
    assert o.methods == ("card", "blik")
    assert "BLIK" in o.definition
    assert o.join_until == date(2026, 11, 12)
    assert o.days == 92
    assert o.cap == 400_000


def test_parse_changed_layout_raises() -> None:
    with pytest.raises(promo_watch.WatchError, match="Nie znaleziono"):
        parsed(PAGE.replace("pozostałych klientów", "inni klienci"))
    with pytest.raises(promo_watch.WatchError, match="Nie znaleziono"):
        promo_watch_velo.parse("zupełnie inna strona", TODAY)


def test_parse_reports_every_missing_field() -> None:
    with pytest.raises(promo_watch.WatchError, match=r"label.*days"):
        promo_watch_velo.parse("Nowe środki na Elastycznym Koncie", TODAY)


@pytest.mark.parametrize(
    ("old", "new", "msg"),
    [
        ("- 4,5% do 400", "- 14,5% do 400", "Stawka"),
        ("BLIKIEM albo - 1% do", "BLIKIEM albo - 5% do", "podstawowa"),
        ("min. 5 transakcji", "min. 0 transakcji", "transakcji"),
        ("do 12.11.2026 r.", "do 12.11.2031 r.", "daty"),
        ("do 12.11.2026 r.", "do 12.11.2025 r.", "daty"),
        ("do 12.11.2026 r.", "do 31.02.2026 r.", "[Dd]at"),
        ("trwa 92 dni", "trwa 920 dni", "okresu"),
        ("kartą do konta lub BLIKIEM albo - 1%", "gotówką albo - 1%", "operacji"),
    ],
)
def test_parse_validation_out_of_range(old: str, new: str, msg: str) -> None:
    assert old in PAGE
    # replace bez limitu: te same zdania występują w nocie raz i w treści strony
    with pytest.raises(promo_watch.WatchError, match=msg):
        parsed(PAGE.replace(old, new))


async def test_refresh_stores_offer_and_creates_review_card(conn: sqlite3.Connection) -> None:
    assert promo_watch_velo.load(conn) is None
    await fetch(conn, PAGE, now(22))
    w = promo_watch_velo.load(conn)
    assert w and w.offer and w.offer.label == "12/2026" and not w.held and not w.error
    assert promo_watch_velo.rates(conn) == w.offer
    assert w.acked == "12/2026" and not w.new_edition and cards(conn, now(22)) == []
    await fetch(conn, PAGE.replace("edycja 12/2026", "edycja 1/2027"), now(23))
    [card] = cards(conn, now(23))
    assert card.kind == "velo_new_edition" and "1/2027" in card.title and card.link == "/piggy#velo"
    assert "4,5%" in card.detail and "5" in card.detail and "12.11" in card.detail
    assert card.severity == "info"


async def test_ack_clears_new_edition(conn: sqlite3.Connection) -> None:
    promo_watch_velo.ack(conn)  # bez odczytu nic nie robi
    assert promo_watch_velo.load(conn) is None
    await fetch(conn, PAGE, now(22))
    await fetch(conn, PAGE.replace("edycja 12/2026", "edycja 1/2027"), now(23))
    w = promo_watch_velo.load(conn)
    assert w and w.new_edition and w.acked == "12/2026"
    promo_watch_velo.ack(conn)
    w = promo_watch_velo.load(conn)
    assert w and not w.new_edition and w.acked == "1/2027" and cards(conn, now(23)) == []
    await fetch(conn, PAGE.replace("edycja 12/2026", "edycja 1/2027"), now(24))  # acked zostaje
    assert not promo_watch_velo.load(conn).new_edition  # type: ignore[union-attr]


async def test_new_edition_makes_new_card_key(conn: sqlite3.Connection) -> None:
    await fetch(conn, PAGE, now(22))
    await fetch(conn, PAGE.replace("edycja 12/2026", "edycja 1/2027"), now(23))
    [old] = cards(conn, now(23))
    inbox.dismiss(conn, old.key, [old])
    assert inbox.visible(conn, cards(conn, now(24))) == []  # obejrzana, ukryta
    nxt = PAGE.replace("edycja 12/2026", "edycja 2/2027")
    await fetch(conn, nxt, now(25))
    [card] = inbox.visible(conn, cards(conn, now(25)))
    assert "2/2027" in card.title and card.key != old.key


async def test_format_change_holds_and_alarms_at_once(conn: sqlite3.Connection) -> None:
    await fetch(conn, PAGE, now(22))
    await fetch(conn, PAGE.replace("pozostałych klientów", "inni"), now(23))
    w = promo_watch_velo.load(conn)
    assert w and w.held and w.error and "WatchError" in w.error
    assert promo_watch_velo.rates(conn) is None  # brak wartości domyślnych ani starych
    kinds = {i.kind: i for i in cards(conn, now(23))}
    assert kinds["velo_held"].severity == "warn" and "wstrzym" in kinds["velo_held"].title.lower()
    assert "velo_new_edition" not in kinds
    await fetch(conn, PAGE, now(24))  # powrót poprawnego układu zdejmuje wstrzymanie
    assert not promo_watch_velo.load(conn).held  # type: ignore[union-attr]
    assert promo_watch_velo.rates(conn) is not None


async def test_out_of_range_value_holds(conn: sqlite3.Connection) -> None:
    await fetch(conn, PAGE.replace("- 4,5% do 400", "- 45% do 400"), now(22))
    w = promo_watch_velo.load(conn)
    assert w and w.held and w.offer is None
    assert promo_watch_velo.rates(conn) is None
    assert [i.kind for i in cards(conn, now(22))] == ["velo_held"]


async def test_network_error_keeps_offer_and_alarms_after_error_days(
    conn: sqlite3.Connection,
) -> None:
    await fetch(conn, PAGE, now(22))

    async def boom() -> str:
        raise OSError("brak sieci")

    for day in (23, 24):
        await promo_watch_velo.refresh(conn, now(day), boom)
    w = promo_watch_velo.load(conn)
    assert w and w.error and "OSError" in w.error and not w.held and w.error_since == now(23)
    assert promo_watch_velo.rates(conn) is not None  # chwilowa awaria nie wstrzymuje
    assert "velo_error" not in {i.kind for i in cards(conn, now(24))}
    late = now(23 + promo_watch.ERROR_ALERT_DAYS)
    assert "velo_error" in {i.kind for i in cards(conn, late)}


async def test_card_disappears_after_offer_ends(conn: sqlite3.Connection) -> None:
    await fetch(conn, PAGE, now(22))
    assert cards(conn, datetime(2027, 2, 13, 8, tzinfo=WAW)) == []  # 12.11 + 92 dni = 14.02


async def test_unexpected_parse_exception_holds_not_network_error(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    await fetch(conn, PAGE, now(22))

    def broken(text: str, today: date) -> promo_watch_velo.Offer:
        raise AttributeError("zmieniony układ")

    monkeypatch.setattr(promo_watch_velo, "parse", broken)
    await fetch(conn, PAGE, now(23))
    w = promo_watch_velo.load(conn)
    assert w and w.held and w.offer is None and w.error and "AttributeError" in w.error
    assert promo_watch_velo.rates(conn) is None  # stara edycja nie zostaje aktywna
    assert [i.kind for i in cards(conn, now(23))] == ["velo_held"]


def test_corrupt_state_loads_as_held(conn: sqlite3.Connection) -> None:
    from budget.storage import db

    db.kv_set(conn, promo_watch_velo.KEY, {"offer": {"label": "12/2026"}, "checked": "nie-data"})
    w = promo_watch_velo.load(conn)
    assert w and w.held and w.offer is None and w.error
    assert promo_watch_velo.rates(conn) is None
    assert [i.kind for i in cards(conn, now(23))] == ["velo_held"]


def test_offer_still_running_after_join_deadline_is_valid() -> None:
    # 12.11 + 92 dni = 14.02.2027: 60 dni po terminie przystąpienia okres trwa, to nie błąd
    assert parsed(today=date(2027, 1, 11)).label == "12/2026"
    with pytest.raises(promo_watch.WatchError):  # >30 dni po końcu okresu — nota wygasła
        parsed(today=date(2027, 3, 20))


async def test_held_card_key_changes_per_episode(conn: sqlite3.Connection) -> None:
    bad = PAGE.replace("pozostałych klientów", "inni")
    await fetch(conn, bad, now(23))
    [first] = [i for i in cards(conn, now(23)) if i.kind == "velo_held"]
    await fetch(conn, PAGE, now(24))
    await fetch(conn, bad, now(26))
    [second] = [i for i in cards(conn, now(26)) if i.kind == "velo_held"]
    assert first.key != second.key  # ukrycie jednego wstrzymania nie wycisza następnego


async def test_any_fetch_exception_sets_error_state(conn: sqlite3.Connection) -> None:
    async def broken() -> str:
        raise RuntimeError("zły certyfikat")

    await promo_watch_velo.refresh(conn, now(22), broken)  # nie rzuca
    w = promo_watch_velo.load(conn)
    assert w and w.error and "RuntimeError" in w.error and w.error_since and not w.held
