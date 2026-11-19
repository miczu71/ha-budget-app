"""Loga sieci przy paragonie: sieć (`lidl`/`biedronka`) → plik SVG w `web/static/stores/`.

Nieznana sieć nie dostaje logo. Pliki z faviconów oficjalnych stron — źródła w `SOURCES.md`.
"""

from __future__ import annotations

from pathlib import Path

from budget.lidl_link import CHAIN_PATTERNS

STATIC_DIR = Path(__file__).parent / "web" / "static" / "stores"

# sieci z `CHAIN_PATTERNS` (nazwa pliku bez .svg = wartość pola `chain` w eksporcie)
STORES: tuple[str, ...] = tuple(CHAIN_PATTERNS)


def slug_for(chain: str | None) -> str | None:
    return chain if chain in STORES else None
