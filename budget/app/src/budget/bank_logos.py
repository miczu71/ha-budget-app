"""Loga banków: nazwa banku → plik SVG w `web/static/banks/`, a dla nieznanego banku monogram.

Dopasowanie po całych słowach (jak `invest.is_client`), więc „ING Bank Śląski” trafia w `ing`,
a „Boeing” nie. Pliki pochodzą z faviconów oficjalnych stron — źródła w `SOURCES.md`.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path
from zlib import crc32

STATIC_DIR = Path(__file__).parent / "web" / "static" / "banks"

# (plik bez .svg, wzorce po casefold); kolejność = pierwszeństwo.
BANKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("velobank", ("velobank", "velo bank")),
    ("millennium", ("millennium",)),
    ("pekao", ("pekao",)),
    ("ing", ("ing",)),
    ("mbank", ("mbank",)),
    ("alior", ("alior",)),
    ("erste", ("erste",)),
    ("bnp", ("bnp",)),
    ("pocztowy", ("pocztowy",)),
    ("inbank", ("inbank",)),
    ("vwbank", ("volkswagen", "vw bank")),
    ("caauto", ("ca auto",)),
    ("obligacje", ("skarb państwa", "obligacje")),
    ("pko", ("pko",)),
    ("citi", ("citi",)),
    ("nest", ("nest",)),
)
_PATTERNS = tuple(
    (slug, re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, pats)) + r")(?!\w)"))
    for slug, pats in BANKS
)


def slug_for(name: str | None) -> str | None:
    folded = (name or "").casefold()
    return next((slug for slug, rx in _PATTERNS if rx.search(folded)), None)


def monogram_svg(name: str) -> str:
    """Kwadratowy kafelek z inicjałami (do dwóch pierwszych słów); kolor stały dla nazwy."""
    words = re.findall(r"[^\W\d_]+", name)
    initials = "".join(w[0] for w in words[:2]).upper() or "?"
    hue = crc32(name.casefold().encode()) % 360
    return (
        '<svg class="bank-logo" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" '
        f'role="img" aria-label="{escape(name, quote=True)}"><rect width="20" height="20" rx="4" '
        f'fill="hsl({hue} 45% 38%)"/><text x="10" y="13.5" text-anchor="middle" font-size="9" '
        f'font-family="sans-serif" font-weight="700" fill="#fff">{escape(initials)}</text></svg>'
    )
