"""Monitor edycji promocji „Nowe środki na Koncie Oszczędnościowym Profit” (M10 E7, decyzja 27).

Nowe środki dostają stawkę promocyjną tylko, gdy są nadwyżką nad saldem z dnia badania sald, a bank
podaje ten dzień w regulaminie dopiero 3–10 dni po fakcie. Dlatego add-on raz dziennie czyta
regulamin (stały adres, PDF), zapisuje ostatnią edycję i prognozuje okno badania następnej: od końca
przystępowania obecnej minus `WINDOW_DAYS` do tego końca (odstępy 0/−5/−6 dni w ed. 65→66, 75→76,
76→77). Alarmy i push budują `inbox` i `summary`; tu jest tylko odczyt, stan i daty.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta

import httpx

from budget.spending import MONTHS_GEN
from budget.storage import db

log = logging.getLogger(__name__)

URL = "https://www.bankmillennium.pl/delegate/managedfiles/591/latest"
KEY = "promo_watch"
WINDOW_DAYS = 6  # dzień badania następnej edycji: [koniec przystępowania − 6 dni, koniec]
ERROR_ALERT_DAYS = 3  # tyle dni nieudanych odczytów → karta w dzwonku
_DATE = r"(\d{1,2} [a-ząćęłńóśźż]+ \d{4})"


class WatchError(ValueError):
    pass


@dataclass(frozen=True)
class Edition:
    number: int
    baseline: date  # dzień badania sald
    start: date  # początek przystępowania
    deadline: date  # koniec przystępowania (ostatni dzień wpłaty nowych środków)
    days: int  # długość okresu promocyjnego

    def window(self) -> tuple[date, date]:
        """Prognoza dnia badania sald NASTĘPNEJ edycji (od, do)."""
        return self.deadline - timedelta(days=WINDOW_DAYS), self.deadline

    def days_to_window(self, today: date) -> int:
        """Dni do początku prognozowanego okna (ujemne, gdy już trwa)."""
        return (self.window()[0] - today).days

    def to_json(self) -> dict[str, object]:
        return {k: v.isoformat() if isinstance(v, date) else v for k, v in asdict(self).items()}

    @classmethod
    def from_json(cls, raw: dict[str, object]) -> Edition:
        d = {k: date.fromisoformat(str(raw[k])) for k in ("baseline", "start", "deadline")}
        return cls(int(str(raw["number"])), days=int(str(raw["days"])), **d)


@dataclass(frozen=True)
class Watch:
    edition: Edition | None
    checked: datetime | None
    error: str | None
    error_since: datetime | None
    pending_confirm: (
        int | None
    )  # numer ostatniej edycji wykrytej PO instalacji (push raz, przez `sent`)
    gap: int | None  # dni od końca poprzedniej edycji do dnia badania nowej (None: brak porównania)


def _day(text: str) -> date:
    d, month, y = text.split()
    if month not in MONTHS_GEN:
        raise WatchError(f"Nieznany miesiąc w regulaminie: {month}")
    return date(int(y), MONTHS_GEN.index(month) + 1, int(d))


def parse(text: str) -> Edition:
    """Edycja z tekstu regulaminu; `WatchError`, gdy układ dokumentu się zmienił."""
    flat = re.sub(r"\s+", " ", text)
    found = {
        "number": re.search(r"edycja (\d{1,3})", flat) or re.search(r"(\d{1,3}) edycji", flat),
        "baseline": re.search(_DATE + r" (?:roku|r\.) ?\(dzień badania sald\)", flat),
        "range": re.search(r"przystąpić od " + _DATE + r" (?:roku|r\.) do " + _DATE, flat),
        "days": re.search(r"trwa (?:przez )?(\d{1,3}) dni", flat),
    }
    missing = [k for k, m in found.items() if m is None]
    if missing:
        raise WatchError("Nie znaleziono w regulaminie: " + ", ".join(missing))
    number, baseline, span, days = (found[k] for k in ("number", "baseline", "range", "days"))
    assert number and baseline and span and days  # mypy: braki wyłapane wyżej
    ed = Edition(
        int(number.group(1)),
        _day(baseline.group(1)),
        _day(span.group(1)),
        _day(span.group(2)),
        int(days.group(1)),
    )
    if not ed.baseline <= ed.start <= ed.deadline:  # inna kolejność = zmiana układu regulaminu
        raise WatchError(f"Niespójne daty regulaminu: {ed.baseline}, {ed.start}, {ed.deadline}")
    return ed


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader  # import leniwy: moduł jest ładowany także w dzwonku

    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


def _raw(conn: sqlite3.Connection) -> dict[str, object]:
    return db.kv_get(conn, KEY) or {}


def _edition(raw: object) -> Edition | None:
    return Edition.from_json(raw) if isinstance(raw, dict) else None


def load(conn: sqlite3.Connection) -> Watch | None:
    """Stan monitora; None, dopóki nie było żadnego odczytu."""
    raw = _raw(conn)
    if not raw:
        return None
    since, checked = raw.get("error_since"), raw.get("checked")
    return Watch(
        _edition(raw.get("edition")),
        datetime.fromisoformat(str(checked)) if checked else None,
        str(raw["error"]) if raw.get("error") else None,
        datetime.fromisoformat(str(since)) if since else None,
        int(str(raw["pending_confirm"])) if raw.get("pending_confirm") else None,
        int(str(raw["gap"])) if raw.get("gap") is not None else None,
    )


async def fetch_text() -> str:
    """Regulamin z bankmillennium.pl jako tekst (PDF czytany poza pętlą zdarzeń)."""
    async with httpx.AsyncClient(
        timeout=20, headers={"User-Agent": "ha-budget-app"}, follow_redirects=True
    ) as client:
        resp = await client.get(URL)
        resp.raise_for_status()
    return await asyncio.to_thread(pdf_text, resp.content)


async def refresh(
    conn: sqlite3.Connection,
    now: datetime,
    get_text: Callable[[], Awaitable[str]] = fetch_text,
) -> None:
    """Jeden odczyt regulaminu; nigdy nie rzuca (błąd trafia do stanu i dzwonka)."""
    raw = _raw(conn)
    raw["checked"] = now.isoformat()
    try:
        ed = parse(await get_text())
    except Exception as exc:  # sieć, PDF, zmiana układu — wszystko ma być widoczne w panelu
        log.warning("Odczyt regulaminu Profit nieudany: %s", exc)
        raw["error"] = f"{type(exc).__name__}: {exc}"[:200]
        if not raw.get("error_since"):
            raw["error_since"] = now.isoformat()
        db.kv_set(conn, KEY, raw)
        return
    prev = _edition(raw.get("edition"))
    if prev is not None and ed.number > prev.number:
        raw["pending_confirm"] = ed.number
        gap = (prev.deadline - ed.baseline).days
        raw["gap"] = gap
        if gap > WINDOW_DAYS:  # prognoza okna była za wąska — widać to w logu i w push
            log.warning("Dzień badania sald %d dni przed końcem poprzedniej edycji", gap)
    raw.update(edition=ed.to_json(), error=None, error_since=None)
    db.kv_set(conn, KEY, raw)
