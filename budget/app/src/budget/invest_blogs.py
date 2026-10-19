"""Oferty z blogów dla agenta inwestycyjnego (M22 E3): RSS + streszczenie wpisu przez LLM.

Raz dziennie czyta kanały z `FEEDS`, wybiera świeże wpisy o lokatach i kontach, a model wyciąga z
nich oferty (bank, stawka, limit, okres, warunki). Wynik ma status „review” — do porównania wchodzi
dopiero po potwierdzeniu przez użytkownika. Do modelu idzie wyłącznie tytuł i streszczenie wpisu z
kanału (bez danych użytkownika, bez pobierania artykułów). Stan (przeczytane wpisy, błąd) w `kv`.
"""

from __future__ import annotations

import asyncio
import html as htmllib
import json
import logging
import re
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any

from budget.invest_sources import Get, fetch
from budget.settings import Settings
from budget.storage import db
from budget.suggest import client
from budget.suggest import engine as suggest
from budget.suggest.client import AIError

log = logging.getLogger(__name__)

# Sonda 2026-10-19: poniższe mają działający kanał i stawki w streszczeniu. Nie nadają się:
# bankier.pl/promocje (pusty kanał) oraz blogi za Cloudflare. Kolejne źródła dopisz tutaj.
FEEDS = (
    "https://subiektywnieofinansach.pl/feed",
    "https://jakoszczedzacpieniadze.pl/feed",  # pisze rzadko
    "https://livesmarter.pl/feed",
    "https://jakdorobic.pl/feed",
    "https://www.bankobranie.pl/rss.xml",
)
KEY = "invest_blogs"
USAGE_KEY = "invest_usage"
MAX_AGE = timedelta(days=30)  # starsza promocja zwykle już nie obowiązuje
OFFER_TTL = timedelta(days=60)  # oferta z bloga starzeje się sama
SEEN_KEEP = 300
MAX_TRIES = 3  # tyle razy wpis może skończyć błędem modelu, zanim go porzucimy
MAX_FAILURES = 2  # tyle błędów z rzędu kończy przebieg (zwykle limit albo awaria routera)
KINDS = ("deposit", "account")
SCHEMA_NAME = "oferty_z_bloga"
TOPIC = re.compile(r"lokat|oszczędnościow", re.I)
FOOTER = re.compile(r"Artykuł\s.*?pochodzi z serwisu.*$", re.S)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "offers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "bank": {"type": "string"},
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "rate": {"type": "number"},
                    "limit": {"type": "number"},
                    "months": {"type": "integer"},
                    "conditions": {"type": "string"},
                    "new_clients_only": {"type": "boolean"},
                },
                "required": [
                    "bank",
                    "kind",
                    "rate",
                    "limit",
                    "months",
                    "conditions",
                    "new_clients_only",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["offers"],
    "additionalProperties": False,
}


class FeedError(ValueError):
    pass


@dataclass(frozen=True)
class Post:
    title: str
    link: str
    published: datetime
    text: str


@dataclass(frozen=True)
class Extracted:
    bank: str
    kind: str
    rate: Decimal
    limit: Decimal | None
    months: int | None
    conditions: str
    new_only: bool


# --- RSS ------------------------------------------------------------------------------------------


def _plain(markup: str) -> str:
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", markup))
    return " ".join(FOOTER.sub("", " ".join(text.split())).split())


def parse_feed(xml: str) -> list[Post]:
    if (
        "<!DOCTYPE" in xml or "<!ENTITY" in xml
    ):  # kanał RSS nie potrzebuje DTD; blokuje XXE i „billion laughs”
        raise FeedError("kanał zawiera DTD")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise FeedError(f"to nie jest kanał RSS ({exc})") from exc
    if root.tag != "rss":
        raise FeedError("to nie jest kanał RSS")
    posts = []
    for it in root.iterfind("./channel/item"):
        link, title = it.findtext("link"), it.findtext("title")
        stamp = it.findtext("pubDate")
        if not (link and title and stamp and link.strip().startswith(("http://", "https://"))):
            continue
        try:
            published = parsedate_to_datetime(stamp).astimezone(UTC)
        except (TypeError, ValueError):
            continue
        posts.append(
            Post(
                " ".join(title.split()),
                link.strip(),
                published,
                _plain(it.findtext("description") or ""),
            )
        )
    return posts


def _utc(moment: datetime) -> datetime:
    """Czas z `Service.now()` ma strefę, w testach bywa bez niej (wtedy UTC)."""
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def wanted(post: Post, now: datetime) -> bool:
    """Świeży wpis, który wygląda na opis oferty (inaczej nie tracimy na niego wywołania)."""
    body = f"{post.title} {post.text}"
    return _utc(now) - post.published <= MAX_AGE and bool(TOPIC.search(body)) and "%" in body


# --- model ----------------------------------------------------------------------------------


def build_prompt(post: Post) -> str:
    return (
        "Z poniższego wpisu blogowego wyciągnij oferty lokat terminowych i kont oszczędnościowych "
        "w polskich bankach. Zwróć tylko oferty, w których tekst podaje bank i oprocentowanie; "
        "niczego nie zgaduj. Okres podany w dniach przelicz na miesiące i zaokrąglij do "
        "najbliższego. Jeśli wpis nie opisuje takiej oferty, zwróć pustą "
        "listę. Pola: bank (nazwa banku), kind (deposit = lokata, account = konto "
        "oszczędnościowe), "
        "rate (% w skali roku), limit (maksymalna kwota, do której obowiązuje stawka, w zł; 0 gdy "
        "tekst jej nie podaje), months (okres lokaty albo trwania promocji w miesiącach; 0 gdy "
        "brak), conditions (warunki jednym zdaniem po polsku; pusty tekst, gdy wpis ich nie "
        "podaje), new_clients_only (true, gdy oferta jest tylko dla nowych klientów).\n\n"
        f"Tytuł: {post.title}\nTreść: {post.text}"
    )


def _decimal(value: object) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def parse_offers(result: dict[str, Any]) -> list[Extracted]:
    """Odpowiedź modelu → tylko pozycje, które przechodzą walidację (resztę odrzucamy po cichu)."""
    out = []
    for raw in result.get("offers") or []:
        if not isinstance(raw, dict):
            continue
        bank = " ".join(str(raw.get("bank", "")).split())[:40]
        kind = raw.get("kind")
        rate = _decimal(raw.get("rate"))
        limit = _decimal(raw.get("limit"))
        months = raw.get("months")
        months = months if isinstance(months, int) and 1 <= months <= 120 else None
        if not bank or kind not in KINDS or rate is None or not 0 < rate <= 20:
            continue
        if kind == "deposit" and months is None:
            continue
        out.append(
            Extracted(
                bank,
                kind,
                Decimal(format(rate.normalize(), "f")),
                limit if limit is not None and limit > 0 else None,
                months,
                " ".join(str(raw.get("conditions", "")).split())[:300],
                bool(raw.get("new_clients_only")),
            )
        )
    return out


# --- zapis i stan --------------------------------------------------------------------------------


def _raw(conn: sqlite3.Connection) -> dict[str, Any]:
    return db.kv_get(conn, KEY) or {}


def error(conn: sqlite3.Connection) -> tuple[str, datetime] | None:
    raw = _raw(conn)
    if not raw.get("error") or not raw.get("error_since"):
        return None
    return str(raw["error"]), datetime.fromisoformat(str(raw["error_since"]))


def _store(conn: sqlite3.Connection, post: Post, found: list[Extracted]) -> None:
    now = db.now_iso()
    for e in found:
        rate = str(e.rate)
        if conn.execute(  # ta sama oferta z innego wpisu albo z rankingu nie wraca do kolejki
            "SELECT 1 FROM invest_offer WHERE archived_at IS NULL AND kind = ? AND rate = ? "
            "AND lower(bank) = lower(?)",
            (e.kind, rate, e.bank),
        ).fetchone():
            continue
        limit = None if e.limit is None else str(e.limit)
        extracted = {"rate": rate, "limit_amount": limit, "months": e.months, "bank": e.bank}
        conn.execute(
            "INSERT INTO invest_offer (kind, bank, rate, limit_amount, months, conditions, "
            "new_clients_only, source, status, url, fetched_at, extracted, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'blog', 'review', ?, ?, ?, ?)",
            (
                e.kind,
                e.bank,
                rate,
                limit,
                e.months,
                e.conditions,
                int(e.new_only),
                post.link,
                now,
                json.dumps(extracted),
                now,
            ),
        )


def _expire(conn: sqlite3.Connection, now: datetime) -> None:
    conn.execute(
        "UPDATE invest_offer SET archived_at = ? WHERE source = 'blog' AND archived_at IS NULL "
        "AND created_at < ?",
        (db.now_iso(), (_utc(now) - OFFER_TTL).isoformat(timespec="seconds")),
    )


async def refresh(
    conn: sqlite3.Connection,
    settings: Settings,
    now: datetime,
    get: Get = fetch,
    call: suggest.Call = client.complete,
) -> None:
    """Nowe wpisy → oferty „do sprawdzenia”; nigdy nie rzuca. Wpis wraca do kolejki, dopóki model
    nie odpowie (błąd AI, limit dobowy)."""
    if not settings.ai_enabled or settings.invest_daily_calls <= 0:
        return
    raw = _raw(conn)
    seen: list[str] = list(raw.get("seen", []))
    tries: dict[str, int] = dict(raw.get("tries", {}))
    errors: list[str] = []
    failed = 0
    posts: list[Post] = []
    pages = await asyncio.gather(*(get(url) for url in FEEDS), return_exceptions=True)
    for url, page in zip(FEEDS, pages, strict=True):
        try:
            if isinstance(page, BaseException):
                raise page
            posts += parse_feed(page)
        except Exception as exc:  # sieć, zmiana układu — ma być widoczne w panelu
            log.warning("Kanał %s nieczytelny: %s", url, exc)
            errors.append(f"{url.split('/')[2]}: {type(exc).__name__}: {exc}")
    today = now.date()
    used = int(suggest.usage(conn, today, USAGE_KEY).get("calls", 0))
    unique = {p.link: p for p in posts}.values()  # ten sam wpis bywa w kilku kanałach
    for post in sorted(unique, key=lambda p: p.published, reverse=True):
        if post.link in seen or not wanted(post, now):
            continue
        if used >= settings.invest_daily_calls:
            break
        used += 1
        try:
            result = await suggest.metered_call(
                conn,
                settings,
                today,
                call,
                key=USAGE_KEY,
                prompt=build_prompt(post),
                schema=SCHEMA,
                schema_name=SCHEMA_NAME,
            )
        except AIError as exc:
            errors.append(f"model: {exc}")
            tries[post.link] = tries.get(post.link, 0) + 1
            if tries[post.link] >= MAX_TRIES:
                seen.append(post.link)  # wpis, z którym model nie radzi sobie, nie blokuje kolejki
            failed += 1
            if failed >= MAX_FAILURES:
                break
            continue
        failed = 0
        _store(conn, post, parse_offers(result))
        seen.append(post.link)
    _expire(conn, now)
    raw["seen"] = seen[-SEEN_KEEP:]
    raw["tries"] = {k: v for k, v in tries.items() if k not in seen}
    if errors:
        raw["error"] = "; ".join(errors)[:300]
        raw["error_since"] = raw.get("error_since") or now.isoformat()
    else:
        raw.update(error=None, error_since=None)
    db.kv_set(conn, KEY, raw)
