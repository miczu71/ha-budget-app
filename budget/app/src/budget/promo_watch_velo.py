"""Monitor edycji promocji Velobanku „Nowe środki na Elastycznym Koncie Oszczędnościowym” (M32 E3).

Raz dziennie czyta publiczną stronę konta (nota prawna oferty), wyciąga stawkę promocyjną
i bazową, termin przystąpienia, długość okresu, próg transakcji bezgotówkowych oraz definicję
liczonych operacji. Wartości poza normą albo zmiana układu strony = stan „wstrzymana”: `rates`
zwraca None i nikt (rekomendacja, licznik) nie dostaje wartości domyślnych. Parametrów konta
tu się nie zapisuje — nowa edycja to tylko karta do wglądu (`inbox.velo_promo_cards`).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from html import unescape
from html.parser import HTMLParser

import httpx

from budget.promo_watch import ERROR_ALERT_DAYS as ERROR_ALERT_DAYS
from budget.promo_watch import WatchError
from budget.storage import db

log = logging.getLogger(__name__)

URL = "https://www.velobank.pl/klienci-indywidualni/oszczednosci/konto-oszczednosciowe.html"
KEY = "promo_watch_velo"
MAX_RATE = 10.0  # stawka w % — wyżej to prawie na pewno błąd parsowania
MIN_TX, MAX_TX = 1, 31  # próg transakcji w miesiącu
MAX_DAYS = 400  # długość okresu promocyjnego
JOIN_PAST_DAYS, JOIN_FUTURE_DAYS = 30, 400  # termin przystąpienia „niedaleko dziś"
METHODS = {"kart": "card", "blik": "blik"}  # słowa definicji → rodzaje operacji
_SKIP = {"script", "style", "noscript"}
_RATE = r"(\d{1,3}(?:,\d+)?)"


@dataclass(frozen=True)
class Offer:
    label: str  # „12/2026"
    promo_rate: float  # % przy spełnionym warunku (klient „pozostały", nie nowy)
    base_rate: float  # % bez spełnionego warunku
    cap: int  # limit nowych środków w zł
    min_transactions: int  # w miesiącu kalendarzowym
    methods: tuple[str, ...]  # „card", „blik"
    definition: str  # dosłowna definicja z regulaminu
    join_until: date  # ostatni dzień wpłaty nowych środków
    days: int  # długość okresu promocyjnego

    def ends_by(self) -> date:
        """Najpóźniejszy koniec okresu promocyjnego (start nie później niż `join_until`)."""
        return self.join_until + timedelta(days=self.days)

    def to_json(self) -> dict[str, object]:
        raw = asdict(self)
        raw["join_until"] = self.join_until.isoformat()
        raw["methods"] = list(self.methods)
        return raw

    @classmethod
    def from_json(cls, raw: dict[str, object]) -> Offer:
        return cls(
            str(raw["label"]),
            float(str(raw["promo_rate"])),
            float(str(raw["base_rate"])),
            int(str(raw["cap"])),
            int(str(raw["min_transactions"])),
            tuple(str(m) for m in raw["methods"]),  # type: ignore[attr-defined]
            str(raw["definition"]),
            date.fromisoformat(str(raw["join_until"])),
            int(str(raw["days"])),
        )


@dataclass(frozen=True)
class Watch:
    offer: (
        Offer | None
    )  # ostatnia poprawnie odczytana edycja (None przy wstrzymaniu z błędu wartości)
    checked: datetime | None
    error: str | None
    error_since: datetime | None
    held: bool  # układ strony/wartości poza normą → rekomendacja wstrzymana


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_text(page: str) -> str:
    """Tekst widoczny na stronie (bez skryptów i stylów), białe znaki zwinięte."""
    p = _Text()
    p.feed(page)
    return re.sub(r"\s+", " ", unescape(" ".join(p.parts)).replace("\xa0", " ")).strip()


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def parse(text: str, today: date) -> Offer:
    """Edycja z tekstu strony; `WatchError`, gdy układ zmienił się albo wartości są poza normą."""
    flat = re.sub(r"\s+", " ", text)
    found = {
        "label": re.search(
            r"Nowe środki na Elastycznym Koncie Oszczędnościowym[”\"] \(edycja (\d{1,2}/\d{4})\)",
            flat,
        ),
        "promo": re.search(
            r"b\) dla pozostałych klientów: - " + _RATE + r"% do (\d{1,4}) tys\. zł .*?"
            r"jeśli wykonasz .*? min\. (\d{1,3}) transakcji bezgotówkowych na koncie osobistym "
            r"(.*?) albo",
            flat,
        ),
        "base": re.search(
            r"b\) dla pozostałych klientów: .*? albo - " + _RATE + r"% do \d{1,4} tys\. zł .*?"
            r"jeśli klient nie spełnił",
            flat,
        ),
        "join": re.search(
            r"wpłacisz nowe środki na Elastyczne Konto Oszczędnościowe do "
            r"(\d{1,2})\.(\d{2})\.(\d{4}) r\.",
            flat,
        ),
        "days": re.search(r"trwa (\d{1,3}) dni kalendarzow", flat),
    }
    missing = [k for k, m in found.items() if m is None]
    if missing:
        raise WatchError("Nie znaleziono na stronie Velobanku: " + ", ".join(missing))
    label, promo, base, join, days = (found[k] for k in ("label", "promo", "base", "join", "days"))
    assert label and promo and base and join and days  # mypy: braki wyłapane wyżej
    try:
        join_until = date(int(join.group(3)), int(join.group(2)), int(join.group(1)))
    except ValueError as exc:
        raise WatchError(f"Błędna data przystąpienia: {join.group(0)}") from exc
    definition = promo.group(4).strip()
    offer = Offer(
        label.group(1),
        _num(promo.group(1)),
        _num(base.group(1)),
        int(promo.group(2)) * 1000,
        int(promo.group(3)),
        tuple(v for k, v in METHODS.items() if k in definition.lower()),
        definition,
        join_until,
        int(days.group(1)),
    )
    _validate(offer, today)
    return offer


def _validate(o: Offer, today: date) -> None:
    if not 0 <= o.base_rate <= MAX_RATE or not 0 <= o.promo_rate <= MAX_RATE:
        raise WatchError(f"Stawka poza normą 0–{MAX_RATE:g}%: {o.promo_rate}% / {o.base_rate}%")
    if o.base_rate >= o.promo_rate:
        raise WatchError(
            f"Stawka podstawowa {o.base_rate}% nie niższa od promocyjnej {o.promo_rate}%"
        )
    if not MIN_TX <= o.min_transactions <= MAX_TX:
        raise WatchError(f"Próg transakcji poza normą {MIN_TX}–{MAX_TX}: {o.min_transactions}")
    if not 1 <= o.days <= MAX_DAYS:
        raise WatchError(f"Długość okresu poza normą 1–{MAX_DAYS} dni: {o.days}")
    lo, hi = today - timedelta(days=JOIN_PAST_DAYS), today + timedelta(days=JOIN_FUTURE_DAYS)
    if not lo <= o.join_until <= hi:
        raise WatchError(f"Termin przystąpienia {o.join_until} poza oknem daty {lo}–{hi}")
    if not o.methods:
        raise WatchError(f"Nierozpoznana definicja operacji: {o.definition[:80]}")


def _raw(conn: sqlite3.Connection) -> dict[str, object]:
    return db.kv_get(conn, KEY) or {}


def load(conn: sqlite3.Connection) -> Watch | None:
    """Stan monitora; None, dopóki nie było żadnego odczytu."""
    raw = _raw(conn)
    if not raw:
        return None
    offer, checked, since = raw.get("offer"), raw.get("checked"), raw.get("error_since")
    return Watch(
        Offer.from_json(offer) if isinstance(offer, dict) else None,
        datetime.fromisoformat(str(checked)) if checked else None,
        str(raw["error"]) if raw.get("error") else None,
        datetime.fromisoformat(str(since)) if since else None,
        bool(raw.get("held")),
    )


def rates(conn: sqlite3.Connection) -> Offer | None:
    """Edycja dla rekomendacji i licznika; None, gdy nie odczytano jej albo jest wstrzymana."""
    w = load(conn)
    return None if w is None or w.held else w.offer


async def fetch_page() -> str:
    """Strona konta oszczędnościowego Velobanku (HTML)."""
    async with httpx.AsyncClient(
        timeout=20, headers={"User-Agent": "ha-budget-app"}, follow_redirects=True
    ) as client:
        resp = await client.get(URL)
        resp.raise_for_status()
    return resp.text


async def refresh(
    conn: sqlite3.Connection,
    now: datetime,
    get_page: Callable[[], Awaitable[str]] = fetch_page,
) -> None:
    """Jeden odczyt; nigdy nie rzuca (błąd trafia do stanu i dzwonka).

    Błąd parsowania/wartości wstrzymuje od razu i kasuje starą edycję (nie podajemy nieaktualnych
    stawek); błąd sieci zachowuje ostatnią edycję i tylko liczy dni do alarmu.
    """
    raw = _raw(conn)
    raw["checked"] = now.isoformat()
    try:
        page = await get_page()
        offer = parse(html_text(page), now.date())
    except Exception as exc:  # sieć, HTTP, zmiana układu — wszystko ma być widoczne w panelu
        log.warning("Odczyt regulaminu Velobanku nieudany: %s", exc)
        raw["error"] = f"{type(exc).__name__}: {exc}"[:200]
        if not raw.get("error_since"):
            raw["error_since"] = now.isoformat()
        if isinstance(exc, WatchError):
            raw["held"] = True
            raw["offer"] = None
        db.kv_set(conn, KEY, raw)
        return
    raw.update(offer=offer.to_json(), error=None, error_since=None, held=False)
    db.kv_set(conn, KEY, raw)
