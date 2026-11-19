"""Loga sieci przy paragonie: sieć → plik SVG, nieznana sieć → brak logo, pakowanie."""

from __future__ import annotations

import pytest

from budget import __version__, store_logos
from budget.web.common import store_logo

CASES = {"lidl": "lidl", "biedronka": "biedronka"}


@pytest.mark.parametrize(("chain", "slug"), CASES.items())
def test_known_store_maps_to_existing_file(chain: str, slug: str) -> None:
    assert store_logos.slug_for(chain) == slug
    assert (store_logos.STATIC_DIR / f"{slug}.svg").is_file()


def test_unknown_store_has_no_logo() -> None:
    assert store_logos.slug_for("zabka") is None
    assert store_logos.slug_for("") is None
    assert store_logos.slug_for(None) is None


def test_every_mapped_slug_has_a_file() -> None:
    for slug in store_logos.STORES:
        assert (store_logos.STATIC_DIR / f"{slug}.svg").is_file(), slug


def test_filter_renders_img_for_biedronka() -> None:
    html = str(store_logo("biedronka", "/ingress"))
    assert 'class="store-logo"' in html
    assert f'src="/ingress/static/stores/biedronka.svg?v={__version__}"' in html


def test_filter_renders_nothing_for_unknown_chain() -> None:
    assert str(store_logo("zabka", "/x")) == ""
    assert str(store_logo(None, "/x")) == ""


def test_sources_file_lists_every_logo() -> None:
    sources = (store_logos.STATIC_DIR / "SOURCES.md").read_text(encoding="utf-8")
    missing = [f.name for f in store_logos.STATIC_DIR.glob("*.svg") if f.name not in sources]
    assert not missing, missing
