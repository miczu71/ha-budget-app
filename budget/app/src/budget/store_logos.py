"""Loga sieci przy paragonie: sieć (`lidl`/`biedronka`) → plik SVG w `web/static/stores/`.

Nieznana sieć nie dostaje logo. Pliki z faviconów oficjalnych stron — źródła w `SOURCES.md`.
"""

from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path(__file__).parent / "web" / "static" / "stores"

# sieci, dla których jest plik SVG (nazwa pliku bez .svg = wartość pola `chain` w eksporcie)
STORES: tuple[str, ...] = ("lidl", "biedronka")


def slug_for(chain: str | None) -> str | None:
    return chain if chain in STORES else None
