"""Oferty z sieci dla agenta inwestycyjnego (M22 E2).

Raz dziennie czyta oprocentowanie obligacji skarbowych (obligacjeskarbowe.pl, stawka 1. roku ze
strony ofert, marża EDO/COI ze strony serii) oraz ranking lokat i kont oszczędnościowych
(bankier.pl/smart) i zapisuje je w `invest_offer`. Bez LLM, bez nowych zależności.

Ranking nie ma pola „bank” — bank rozpoznaje `guess_bank` słownikiem po nazwie produktu i slugu
adresu; nierozpoznany wpis dostaje status „review” i nie liczy się, dopóki użytkownik go nie
potwierdzi. Linki „Sprawdź ofertę” (`/e/lead…`) zabrania robots.txt, więc zapisujemy tylko link
do opisu oferty. Wzorzec jak `wibor`: błąd nie rzuca, ląduje w `kv` i w dzwonku.
"""

from __future__ import annotations

import html as htmllib
import logging
import re
import sqlite3
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx

from budget import invest
from budget.storage import db

log = logging.getLogger(__name__)

BONDS_ROOT = "https://www.obligacjeskarbowe.pl"
BONDS_URL = BONDS_ROOT + "/oferta-obligacji/"
RANKING_ROOT = "https://www.bankier.pl"
DEPOSITS_URL = RANKING_ROOT + "/smart/lokaty"
ACCOUNTS_URL = RANKING_ROOT + "/smart/konta-oszczednosciowe"
KEY = "invest_sources"
BOND_ISSUER = "Skarb Państwa"
INTERVAL = timedelta(hours=20)  # restart add-onu nie odpytuje stron drugi raz tego samego dnia
ERROR_ALERT_DAYS = 3  # tyle dni nieudanych odczytów → karta w dzwonku
TOP = 10  # tyle najlepszych wpisów z każdego rankingu
MIN_LIMIT = Decimal(1000)  # mniejsza kwota „do X zł” to zwykle premia, nie limit

Get = Callable[[str], Awaitable[str]]


class SourceError(ValueError):
    pass


@dataclass(frozen=True)
class Found:
    """Wpis rankingu po sparsowaniu."""

    kind: str  # deposit | account
    bank: str
    rate: Decimal
    url: str
    months: int | None = None
    limit: Decimal | None = None
    conditions: str = ""
    new_only: bool = False
    review: bool = False  # banku nie rozpoznano


# --- parsowanie: obligacje -------------------------------------------------------------------

_CARD_PATH = re.compile(r'href="(/oferta-obligacji/[^"]+)"')
_CARD_RATE = re.compile(r"(\d+,\d+)\s*<sub>")
_CARD_SYMBOL = re.compile(r"\(symbol:\s*([A-Z]+)\)")
_MARGIN = re.compile(r"mar[żz]a\s+(\d+,\d+)\s*%")


def _dec(text: str) -> Decimal:
    try:
        return Decimal(text.replace(",", ".").replace("\xa0", "").replace(" ", ""))
    except InvalidOperation as exc:
        raise SourceError(f"Nieczytelna liczba: {text!r}") from exc


def parse_bonds(page: str) -> dict[str, tuple[Decimal, str]]:
    """Rodzaj obligacji → (stawka 1. roku, ścieżka strony serii). Tylko rodzaje z `invest.BONDS`."""
    out: dict[str, tuple[Decimal, str]] = {}
    for chunk in page.split('class="product-card"')[1:]:
        path, rate, symbol = (
            _CARD_PATH.search(chunk),
            _CARD_RATE.search(chunk),
            _CARD_SYMBOL.search(chunk),
        )
        if path and rate and symbol and (kind := symbol.group(1).lower()) in invest.BONDS:
            out[kind] = (_dec(rate.group(1)), path.group(1))
    if not out:
        raise SourceError("Nie znaleziono obligacji na stronie ofert")
    return out


def parse_margin(page: str) -> Decimal:
    """Marża ponad inflację (p.p.) ze strony serii obligacji indeksowanych."""
    m = _MARGIN.search(htmllib.unescape(page))
    if m is None:
        raise SourceError("Nie znaleziono marży na stronie serii")
    return _dec(m.group(1))


# --- parsowanie: ranking ---------------------------------------------------------------------

_NAME = re.compile(
    r'<a href="(/smart/[^"]+)"[^>]*class="button link-button -text">(.*?)(?:<span|</a>)', re.S
)
_RATE = re.compile(r'Oprocentowanie</div><div class="[^"]*">\s*(\d+,\d+)\s*%')
_PERIOD = re.compile(r'-period">.*?value">\s*(\d+)', re.S)
_TIP = re.compile(r"tooltip__content[^>]*>.*?<div>(.*?)</div></div>", re.S)
_TAGS = re.compile(r"<[^>]+>")
_DAYS = re.compile(r"(\d+)\s*dni")
_MONTHS = re.compile(r"(\d+)\s*miesi")
_LIMIT = re.compile(
    r"(?:do(?:\s+kwoty)?|max\.?|maksymalnie)\s+(\d[\d\s\xa0]*\d)\s*zł(?!\s*(?:premi|bonus|nagrod|zwrot))",
    re.I,
)
_NEW_ONLY = re.compile(
    r"nowych klient|nowy klient|nowym klient|klient\w*,?\s+którzy\s+nie\s+(?:posiada|miel|mają"
    r"|byli|korzyst)|nie\s+(?:posiadał|był|miał)\w*\s+(?:konta|klient)",
    re.I,
)

# (nazwa, wzorzec na znormalizowanym „-nazwa-slug-”); pierwszy pasujący wygrywa
BANKS: tuple[tuple[str, str], ...] = (
    ("Santander Consumer Bank", r"-santander-consumer"),
    ("Santander Bank Polska", r"-santander"),
    ("ING Bank Śląski", r"-ing-"),
    ("Bank Pekao", r"-pekao"),
    ("PKO Bank Polski", r"-pko-"),
    ("mBank", r"-mbank"),
    ("Bank Millennium", r"-millennium"),
    ("Alior Bank", r"-alior"),
    ("VeloBank", r"-velo-?bank"),
    ("Credit Agricole", r"-credit-agricole"),
    ("CA Auto Bank", r"-ca-auto"),
    ("BNP Paribas", r"-bnp-"),
    ("Citi Handlowy", r"-citi-|-handlowy"),
    ("Inbank", r"-inbank"),
    ("Renault Bank", r"-renault-bank"),
    ("Volkswagen Bank", r"-volkswagen"),
    ("Toyota Bank", r"-toyota"),
    ("Nest Bank", r"-nest-bank"),
    ("BFF Banking Group", r"-bff-"),
    ("Bank Pocztowy", r"-pocztowy"),
    ("BOŚ Bank", r"-bos-bank"),
    ("Getin Bank", r"-getin"),
    ("Idea Bank", r"-idea-bank"),
    ("Plus Bank", r"-plus-bank"),
    ("Aion Bank", r"-aion-"),
    ("Bank Nowy BFG", r"-nowy-bank"),
    ("Erste Bank", r"-erste"),
)


def _norm(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return "-" + re.sub(r"[^a-z0-9]+", "-", plain).strip("-") + "-"


def guess_bank(title: str, slug: str) -> str | None:
    """Bank ze słownika po nazwie produktu i slugu adresu; None, gdy nic nie pasuje."""
    text = _norm(f"{title} {slug}")
    return next((name for name, pattern in BANKS if re.search(pattern, text)), None)


def _clean(text: str) -> str:
    return " ".join(htmllib.unescape(_TAGS.sub(" ", text)).split())


def _entry(chunk: str, kind: str) -> Found | None:
    name, rate = _NAME.search(chunk), _RATE.findall(chunk)
    if name is None or not rate:
        return None
    path, title = name.group(1), _clean(name.group(2))
    value = _dec(rate[-1])
    tip = _TIP.search(chunk)
    cond = _clean(tip.group(1)) if tip else ""
    months: int | None = None
    if period := _PERIOD.search(chunk):
        months = int(period.group(1))
    elif kind == "account":
        if days := _DAYS.search(cond):
            months = max(round(int(days.group(1)) / 30.4), 1)
        elif mon := _MONTHS.search(cond):
            months = int(mon.group(1))
    limit = None
    if (m := _LIMIT.search(f"{title} {_clean(chunk)}")) and (cap := _dec(m.group(1))) >= MIN_LIMIT:
        limit = cap
    bank = guess_bank(title, path.split("?")[0].rsplit("/", 1)[-1])
    return Found(
        kind,
        (bank or title)[:40],
        value,
        RANKING_ROOT + path,
        months,
        limit,
        cond[:300],
        bool(_NEW_ONLY.search(f"{title} {cond}")),
        bank is None,
    )


def parse_ranking(page: str, kind: str) -> list[Found]:
    """Najlepsze wpisy rankingu lokat (`deposit`) albo kont (`account`) o stawce > 0."""
    entries = [e for chunk in page.split('class="offers__item "')[1:] if (e := _entry(chunk, kind))]
    if not entries:
        raise SourceError("Nie znaleziono ofert w rankingu")
    return [e for e in entries if e.rate > 0][:TOP]


# --- zapis ---------------------------------------------------------------------------------------


def _upsert(
    conn: sqlite3.Connection, where: str, args: tuple[object, ...], row: dict[str, object]
) -> int:
    """Aktualizuje wpis pasujący do `where` (nigdy odrzucony; status i bank zostają, jeśli
    użytkownik je zmienił) albo dodaje nowy; zwraca id."""
    now = db.now_iso()
    found = conn.execute(f"SELECT id, status FROM invest_offer WHERE {where}", args).fetchone()
    if found is None:
        cols = {**row, "fetched_at": now, "created_at": now}
        conn.execute(
            f"INSERT INTO invest_offer ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            tuple(cols.values()),
        )
        return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    if found["status"] != "rejected":
        keep = ("status", "bank", "kind", "source")
        sets = {k: v for k, v in row.items() if k not in keep}
        sets.update(fetched_at=now, archived_at=None)
        conn.execute(
            f"UPDATE invest_offer SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?",
            (*sets.values(), found["id"]),
        )
    return int(found["id"])


def _archive_missing(
    conn: sqlite3.Connection, source: str, kinds: tuple[str, ...], keep: set[int]
) -> None:
    marks = ", ".join("?" * len(kinds))
    for r in conn.execute(
        "SELECT id FROM invest_offer WHERE source = ? AND archived_at IS NULL "
        f"AND kind IN ({marks})",
        (source, *kinds),
    ).fetchall():
        if r["id"] not in keep:
            conn.execute(
                "UPDATE invest_offer SET archived_at = ? WHERE id = ?", (db.now_iso(), r["id"])
            )


async def _bonds(conn: sqlite3.Connection, get: Get) -> None:
    quotes = parse_bonds(await get(BONDS_URL))
    margins = {
        kind: parse_margin(await get(BONDS_ROOT + path))
        for kind, (_, path) in quotes.items()
        if kind in invest.INDEXED
    }
    keep: set[int] = set()
    for kind, (rate, path) in quotes.items():
        series = path.strip("/").rsplit("/", 1)[-1].upper()
        margin = margins.get(kind)
        keep.add(
            _upsert(
                conn,
                "source = 'bonds' AND kind = ?",
                (kind,),
                {
                    "kind": kind,
                    "bank": BOND_ISSUER,
                    "rate": str(rate),
                    "margin": None if margin is None else str(margin),
                    "conditions": f"Seria {series}",
                    "source": "bonds",
                    "status": "confirmed",
                    "url": BONDS_ROOT + path,
                },
            )
        )
    _archive_missing(conn, "bonds", tuple(invest.BONDS), keep)


async def _ranking(conn: sqlite3.Connection, get: Get, url: str, kind: str) -> None:
    keep: set[int] = set()
    for f in parse_ranking(await get(url), kind):
        keep.add(
            _upsert(
                conn,
                "source = 'ranking' AND kind = ? AND url = ? "
                "AND IFNULL(months, -1) = ? AND rate = ?",
                (kind, f.url, -1 if f.months is None else f.months, str(f.rate)),
                {
                    "kind": kind,
                    "bank": f.bank,
                    "rate": str(f.rate),
                    "limit_amount": None if f.limit is None else str(f.limit),
                    "months": f.months,
                    "conditions": f.conditions,
                    "new_clients_only": int(f.new_only),
                    "source": "ranking",
                    "status": "review" if f.review else "confirmed",
                    "url": f.url,
                },
            )
        )
    _archive_missing(conn, "ranking", (kind,), keep)


# --- odczyt i stan -------------------------------------------------------------------------------


async def fetch(url: str) -> str:
    async with httpx.AsyncClient(
        timeout=20, headers={"User-Agent": "ha-budget-app"}, follow_redirects=True
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


def _raw(conn: sqlite3.Connection) -> dict[str, object]:
    return db.kv_get(conn, KEY) or {}


def due(conn: sqlite3.Connection, now: datetime) -> bool:
    """Czy minęło dość czasu od ostatniego odczytu."""
    checked = _raw(conn).get("checked")
    return checked is None or now - datetime.fromisoformat(str(checked)) >= INTERVAL


def checked(conn: sqlite3.Connection) -> datetime | None:
    raw = _raw(conn).get("checked")
    return datetime.fromisoformat(str(raw)) if raw else None


def error(conn: sqlite3.Connection) -> tuple[str, datetime] | None:
    """Ostatni błąd odczytu i od kiedy trwa (None: odczyt działa)."""
    raw = _raw(conn)
    if not raw.get("error") or not raw.get("error_since"):
        return None
    return str(raw["error"]), datetime.fromisoformat(str(raw["error_since"]))


async def refresh(conn: sqlite3.Connection, now: datetime, get: Get = fetch) -> None:
    """Odczyt wszystkich źródeł; nigdy nie rzuca. Każde źródło osobno: awaria jednego (np. zmiana
    układu rankingu) nie blokuje reszty, a błąd trafia do stanu i dzwonka."""
    raw = _raw(conn)
    raw["checked"] = now.isoformat()
    errors: list[str] = []
    jobs = (
        ("obligacje", _bonds(conn, get)),
        ("lokaty", _ranking(conn, get, DEPOSITS_URL, "deposit")),
        ("konta", _ranking(conn, get, ACCOUNTS_URL, "account")),
    )
    for label, job in jobs:
        try:
            await job
        except Exception as exc:  # sieć, zmiana układu strony — wszystko ma być widoczne w panelu
            log.warning("Odczyt źródła %s nieudany: %s", label, exc)
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
    if errors:
        raw["error"] = "; ".join(errors)[:300]
        if not raw.get("error_since"):
            raw["error_since"] = now.isoformat()
    else:
        raw.update(error=None, error_since=None)
    db.kv_set(conn, KEY, raw)
