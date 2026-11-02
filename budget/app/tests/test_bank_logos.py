"""Loga banków: mapowanie nazw na pliki, monogram dla nieznanych, pakowanie."""

from __future__ import annotations

import pytest

from budget import __version__, bank_logos
from budget.web.common import bank_logo

CASES = {
    "VeloBank": "velobank",
    "Velo Bank": "velobank",
    "Bank Millennium": "millennium",
    "Millennium": "millennium",
    "Bank Pekao": "pekao",
    "Pekao SA": "pekao",
    "ING More": "ing",
    "ING Bank Śląski": "ing",
    "mBank": "mbank",
    "Alior Bank": "alior",
    "Erste Bank": "erste",
    "BNP Paribas": "bnp",
    "Pocztowy": "pocztowy",
    "Bank Pocztowy": "pocztowy",
    "Inbank": "inbank",
    "Volkswagen Bank": "vwbank",
    "CA Auto Bank": "caauto",
    "Skarb Państwa": "obligacje",
    "Obligacje skarbowe": "obligacje",
    "PKO BP": "pko",
    "PKO Bank Polski": "pko",
    "Citi Handlowy": "citi",
    "Nest Bank": "nest",
}


@pytest.mark.parametrize(("name", "slug"), CASES.items())
def test_known_banks_map_to_existing_file(name: str, slug: str) -> None:
    assert bank_logos.slug_for(name) == slug
    assert (bank_logos.STATIC_DIR / f"{slug}.svg").is_file()


def test_every_mapped_slug_has_a_file() -> None:
    for slug, _ in bank_logos.BANKS:
        assert (bank_logos.STATIC_DIR / f"{slug}.svg").is_file(), slug


def test_word_boundaries() -> None:
    assert bank_logos.slug_for("Boeing Finance") is None  # „ing” w środku słowa
    assert bank_logos.slug_for("") is None
    assert bank_logos.slug_for("Bank X") is None


def test_filter_renders_img_for_known_bank() -> None:
    html = str(bank_logo("ING More", "/ingress"))
    assert 'class="bank-logo"' in html
    assert f'src="/ingress/static/banks/ing.svg?v={__version__}"' in html


def test_filter_renders_monogram_for_unknown_bank() -> None:
    html = str(bank_logo("Bank Zielony", "/x"))
    assert "<svg" in html and "bank-logo" in html and ">BZ<" in html
    assert "<img" not in html
    assert str(bank_logo("Bank Zielony", "/x")) == html  # kolor z hasha jest stały


def test_filter_escapes_name_and_handles_empty() -> None:
    assert str(bank_logo("", "/x")) == ""
    assert str(bank_logo(None, "/x")) == ""
    assert "<script" not in str(bank_logo("<script>alert(1)</script>", "/x"))


def test_sources_file_lists_every_logo() -> None:
    sources = (bank_logos.STATIC_DIR / "SOURCES.md").read_text(encoding="utf-8")
    missing = [f.name for f in bank_logos.STATIC_DIR.glob("*.svg") if f.name not in sources]
    assert not missing, missing
