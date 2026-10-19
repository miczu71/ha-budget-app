"""Oferty z blogów (M22 E3): RSS, filtr wpisów, odpowiedź LLM, zapis, potwierdzanie, pomiar."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from budget import invest
from budget import invest_blogs as blogs
from budget.settings import Settings
from budget.suggest.client import AIError

from .test_categorize_engine import conn

__all__ = ["conn"]

NOW = datetime(2026, 10, 19, 7, 0)
AI = Settings(ai_base_url="http://router:3003/v1", ai_api_key="k", invest_daily_calls=3)
FEED_URL = blogs.FEEDS[0]


def item(title: str, link: str, day: str, text: str) -> str:
    return (
        f"<item><title>{title}</title><link>{link}</link><pubDate>{day} 08:00:00 +0000</pubDate>"
        f'<description><![CDATA[<p>{text}</p><p>Artykuł <a href="{link}">x</a> pochodzi z serwisu '
        f'<a href="https://blog.example">Blog</a>.</p>]]></description></item>'
    )


def feed(*items: str) -> str:
    body = "".join(items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{body}</channel></rss>'


DEPOSIT = item(
    "Nowa lokata w Banku A",
    "https://blog.example/lokata-a/",
    "Thu, 15 Oct 2026",
    "Bank A uruchamia lokatę 5% w skali roku przez pięć miesięcy, do 50 000 zł. Nowi klienci.",
)
OLD = item(
    "Stara lokata w Banku B",
    "https://blog.example/lokata-b/",
    "Mon, 01 Jun 2026",
    "Lokata 6% przez rok.",
)
OFFTOPIC = item(
    "Jak kupić auto?", "https://blog.example/auto/", "Mon, 19 Oct 2026", "Kupno samochodu i kredyt."
)

ANSWER = {
    "offers": [
        {
            "bank": "Bank A",
            "kind": "deposit",
            "rate": 5.0,
            "limit": 50000,
            "months": 5,
            "conditions": "Lokata 5% przez 5 mies.",
            "new_clients_only": True,
        }
    ]
}


class Fake:
    def __init__(self, *answers: dict[str, Any] | Exception) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    async def __call__(self, **kw: Any) -> tuple[dict[str, Any], int]:
        self.prompts.append(kw["prompt"])
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a, 100


def getter(xml: str):
    async def get(url: str) -> str:
        return xml

    return get


def rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM invest_offer WHERE source = 'blog' ORDER BY id").fetchall()


# --- RSS i filtr ------------------------------------------------------------------------------


def test_parse_feed_strips_html_and_footer() -> None:
    [post] = blogs.parse_feed(feed(DEPOSIT))
    assert post.title == "Nowa lokata w Banku A"
    assert post.link == "https://blog.example/lokata-a/"
    assert post.published == datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
    assert (
        "lokatę 5%" in post.text
        and "<p>" not in post.text
        and "pochodzi z serwisu" not in post.text
    )


def test_parse_feed_rejects_garbage() -> None:
    with pytest.raises(blogs.FeedError):
        blogs.parse_feed("<html>nie rss</html>")


def test_parse_feed_rejects_dtd() -> None:
    with pytest.raises(blogs.FeedError):
        blogs.parse_feed('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "b">]><rss><channel/></rss>')


def test_wanted_filters_topic_and_age() -> None:
    posts = {p.link: p for p in blogs.parse_feed(feed(DEPOSIT, OLD, OFFTOPIC))}
    assert blogs.wanted(posts["https://blog.example/lokata-a/"], NOW)
    assert not blogs.wanted(posts["https://blog.example/lokata-b/"], NOW)  # starsze niż MAX_AGE
    assert not blogs.wanted(posts["https://blog.example/auto/"], NOW)  # bez słów o ofertach


# --- odpowiedź modelu ---------------------------------------------------------------------------


def test_parse_offers_validates() -> None:
    [o] = blogs.parse_offers(ANSWER)
    assert (o.bank, o.kind, o.rate, o.limit, o.months, o.new_only) == (
        "Bank A",
        "deposit",
        Decimal("5"),
        Decimal("50000"),
        5,
        True,
    )
    bad = {
        "offers": [
            {**ANSWER["offers"][0], "rate": 0},  # stawka poza zakresem
            {**ANSWER["offers"][0], "kind": "edo"},  # rodzaj spoza listy
            {**ANSWER["offers"][0], "bank": " "},  # bez banku
            {**ANSWER["offers"][0], "kind": "deposit", "months": 0},  # lokata bez okresu
            {**ANSWER["offers"][0], "rate": 5.5, "limit": 0, "months": 0, "kind": "account"},
        ]
    }
    [only] = blogs.parse_offers(bad)
    assert only.kind == "account" and only.limit is None and only.months is None


# --- refresh --------------------------------------------------------------------------------------


async def test_refresh_stores_review_offer_with_link(conn: sqlite3.Connection) -> None:
    fake = Fake(ANSWER)
    await blogs.refresh(conn, AI, NOW, getter(feed(DEPOSIT, OFFTOPIC)), fake)
    [r] = rows(conn)
    assert (r["status"], r["bank"], r["kind"], r["rate"], r["months"]) == (
        "review",
        "Bank A",
        "deposit",
        "5",
        5,
    )
    assert (r["limit_amount"], r["new_clients_only"], r["url"]) == (
        "50000",
        1,
        "https://blog.example/lokata-a/",
    )
    assert json.loads(r["extracted"])["rate"] == "5" and r["verdict"] is None
    assert len(fake.prompts) == 1  # wpis spoza tematu nie idzie do modelu
    assert "lokatę 5%" in fake.prompts[0]


async def test_refresh_sends_only_post_text(conn: sqlite3.Connection) -> None:
    invest.save_bank(conn, "Moj Bank Tajny")
    fake = Fake(ANSWER)
    await blogs.refresh(conn, AI, NOW, getter(feed(DEPOSIT)), fake)
    assert "Tajny" not in fake.prompts[0]


async def test_refresh_does_not_repeat_seen_posts(conn: sqlite3.Connection) -> None:
    fake = Fake(ANSWER)
    get = getter(feed(DEPOSIT))
    await blogs.refresh(conn, AI, NOW, get, fake)
    await blogs.refresh(conn, AI, NOW, get, fake)
    assert len(fake.prompts) == 1 and len(rows(conn)) == 1


async def test_refresh_respects_daily_limit(conn: sqlite3.Connection) -> None:
    posts = [
        item(
            f"Lokata {i}", f"https://blog.example/{i}/", "Thu, 15 Oct 2026", "Lokata 5% przez rok."
        )
        for i in range(5)
    ]
    fake = Fake(*[{"offers": []}] * 5)
    await blogs.refresh(conn, AI, NOW, getter(feed(*posts)), fake)
    assert len(fake.prompts) == 3  # invest_daily_calls
    await blogs.refresh(conn, AI, NOW, getter(feed(*posts)), fake)
    assert len(fake.prompts) == 3  # limit dobowy zużyty


async def test_ai_error_keeps_post_for_retry_and_surfaces(conn: sqlite3.Connection) -> None:
    get = getter(feed(DEPOSIT))
    await blogs.refresh(conn, AI, NOW, get, Fake(AIError("limit")))
    assert rows(conn) == []
    state = blogs.error(conn)
    assert state is not None and "limit" in state[0]
    await blogs.refresh(conn, AI, NOW, get, Fake(ANSWER))
    assert len(rows(conn)) == 1 and blogs.error(conn) is None


async def test_disabled_without_ai_or_limit(conn: sqlite3.Connection) -> None:
    fake = Fake(ANSWER)
    await blogs.refresh(conn, Settings(), NOW, getter(feed(DEPOSIT)), fake)
    await blogs.refresh(
        conn,
        Settings(ai_base_url="http://r/v1", invest_daily_calls=0),
        NOW,
        getter(feed(DEPOSIT)),
        fake,
    )
    assert fake.prompts == [] and rows(conn) == []


async def test_feed_failure_is_recorded_not_raised(conn: sqlite3.Connection) -> None:
    async def boom(url: str) -> str:
        raise OSError("sieć")

    await blogs.refresh(conn, AI, NOW, boom, Fake())
    state = blogs.error(conn)
    assert state is not None and "sieć" in state[0]


async def test_expired_blog_offers_are_archived(conn: sqlite3.Connection) -> None:
    await blogs.refresh(conn, AI, NOW, getter(feed(DEPOSIT)), Fake(ANSWER))
    await blogs.refresh(conn, AI, datetime(2026, 12, 30, 7, 0), getter(feed()), Fake())
    assert rows(conn)[0]["archived_at"] is not None


async def test_blog_offer_hidden_for_existing_client_only_when_new_only(
    conn: sqlite3.Connection,
) -> None:
    await blogs.refresh(conn, AI, NOW, getter(feed(DEPOSIT)), Fake(ANSWER))
    invest.save_bank(conn, "Bank A")
    [o] = [o for o in invest.all_offers(conn) if o.source == "blog"]
    assert o.new_only and invest.is_hidden(o, [b.name for b in invest.all_banks(conn)])


# --- potwierdzanie i pomiar trafności ---------------------------------------------------------


async def _one(conn: sqlite3.Connection) -> int:
    await blogs.refresh(conn, AI, NOW, getter(feed(DEPOSIT)), Fake(ANSWER))
    return int(rows(conn)[0]["id"])


async def test_confirm_unchanged_is_clean(conn: sqlite3.Connection) -> None:
    oid = await _one(conn)
    invest.confirm_offer(
        conn,
        oid,
        "Bank A",
        {
            "rate": "5",
            "limit_amount": "50000",
            "months": "5",
            "conditions": "Lokata 5% przez 5 mies.",
        },
    )
    r = rows(conn)[0]
    assert (r["status"], r["verdict"]) == ("confirmed", "clean")
    assert invest.blog_accuracy(conn) == (1, 1)


async def test_confirm_with_fix_is_fixed_and_saved(conn: sqlite3.Connection) -> None:
    oid = await _one(conn)
    invest.confirm_offer(
        conn,
        oid,
        "Bank A",
        {"rate": "5,5", "limit_amount": "50000", "months": "6", "conditions": "x"},
    )
    r = rows(conn)[0]
    assert (r["status"], r["verdict"], Decimal(r["rate"]), r["months"]) == (
        "confirmed",
        "fixed",
        Decimal("5.5"),
        6,
    )
    assert invest.blog_accuracy(conn) == (0, 1)


async def test_confirm_with_invalid_field_raises_and_keeps_review(conn: sqlite3.Connection) -> None:
    oid = await _one(conn)
    with pytest.raises(invest.InvestError):
        invest.confirm_offer(
            conn,
            oid,
            "Bank A",
            {"rate": "abc", "limit_amount": "", "months": "5", "conditions": ""},
        )
    assert rows(conn)[0]["status"] == "review"


async def test_reject_counts_against_accuracy(conn: sqlite3.Connection) -> None:
    oid = await _one(conn)
    invest.archive_offer(conn, oid)
    r = rows(conn)[0]
    assert (r["status"], r["verdict"]) == ("rejected", "rejected")
    assert invest.blog_accuracy(conn) == (0, 1)


async def test_removing_confirmed_offer_keeps_verdict(conn: sqlite3.Connection) -> None:
    oid = await _one(conn)
    invest.confirm_offer(
        conn,
        oid,
        "Bank A",
        {
            "rate": "5",
            "limit_amount": "50000",
            "months": "5",
            "conditions": "Lokata 5% przez 5 mies.",
        },
    )
    invest.archive_offer(conn, oid)
    assert rows(conn)[0]["verdict"] == "clean"


async def test_bad_response_skips_post_and_continues(conn: sqlite3.Connection) -> None:
    other = item("Lokata 2", "https://blog.example/2/", "Wed, 14 Oct 2026", "Lokata 4% przez rok.")
    get = getter(feed(DEPOSIT, other))
    fake = Fake(AIError("zły format"), {"offers": []})
    await blogs.refresh(conn, AI, NOW, get, fake)
    assert len(fake.prompts) == 2  # błąd przy pierwszym wpisie nie blokuje drugiego


async def test_run_stops_after_two_failures_and_gives_up_after_three_tries(
    conn: sqlite3.Connection,
) -> None:
    posts = [
        item(f"Lokata {i}", f"https://blog.example/{i}/", "Thu, 15 Oct 2026", "Lokata 5% rok.")
        for i in range(3)
    ]
    get = getter(feed(*posts))
    fake = Fake(*[AIError("x")] * 9)
    for _ in range(3):
        await blogs.refresh(conn, AI.model_copy(update={"invest_daily_calls": 50}), NOW, get, fake)
    assert len(fake.prompts) == 6  # 2 błędy na przebieg
    again = Fake({"offers": []})
    await blogs.refresh(conn, AI.model_copy(update={"invest_daily_calls": 50}), NOW, get, again)
    assert len(again.prompts) == 1  # trzeci wpis ma dopiero pierwszą próbę, dwa pierwsze porzucone


async def test_refresh_accepts_timezone_aware_now(conn: sqlite3.Connection) -> None:
    """`Service.now()` ma strefę — naiwne porównanie z datą z RSS się wywalało."""
    aware = datetime(2026, 10, 19, 9, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
    await blogs.refresh(conn, AI, aware, getter(feed(DEPOSIT)), Fake(ANSWER))
    assert len(rows(conn)) == 1 and blogs.error(conn) is None


# --- poprawki z code-review (E3/E4) ---


def test_feed_ignores_non_http_links() -> None:
    bad = item("Lokata", "javascript:alert(1)", "Thu, 15 Oct 2026", "Lokata 5%.")
    assert blogs.parse_feed(feed(bad)) == []


def test_whole_ten_rate_is_not_scientific_notation() -> None:
    raw = {**ANSWER["offers"][0], "rate": 10}
    (e,) = blogs.parse_offers({"offers": [raw]})
    assert str(e.rate) == "10"


async def test_error_is_reported_again_after_a_recovery(conn: sqlite3.Connection) -> None:
    await blogs.refresh(conn, AI, NOW, getter(feed(OFFTOPIC)), Fake())  # sukces: błąd wyczyszczony
    assert blogs.error(conn) is None
    await blogs.refresh(conn, AI, NOW, getter("nie xml"), Fake())
    assert blogs.error(conn) is not None


async def test_same_offer_from_second_post_is_stored_once(conn: sqlite3.Connection) -> None:
    again = item("Ta sama lokata", "https://blog.example/inna/", "Fri, 16 Oct 2026", "Lokata 5%.")
    await blogs.refresh(conn, AI, NOW, getter(feed(DEPOSIT, again)), Fake(ANSWER, ANSWER))
    assert len(rows(conn)) == 1
