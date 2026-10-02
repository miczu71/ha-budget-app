"""Słownik sieci i nazwa sprzedawcy — opisy syntetyczne w formatach Millennium."""

from __future__ import annotations

import pytest

from budget.categorize import merchants, taxonomy
from budget.categorize.merchants import DictionaryError
from budget.storage import db


def _slug(text: str) -> str | None:
    e = merchants.builtin().match(text)
    return e.slug if e else None


def _name(text: str) -> str | None:
    e = merchants.builtin().match(text)
    return e.name if e else None


def test_builtin_slugs_are_leaf_categories() -> None:
    leaves = {c.slug for c in taxonomy.leaves(db.connect(":memory:")).values()}
    d = merchants.builtin()
    assert d.version >= 1
    assert len(d.entries) > 300
    assert {e.slug for e in d.entries} <= leaves


@pytest.mark.parametrize(
    ("text", "slug", "name"),
    [
        ("ZABKA Z1234 K.1 UL. TESTOWA 1 XYZ POL 2026-01-02", "spozywcze", "Żabka"),
        ("JMP BIEDRONKA 123 UL. TESTOWA XYZ POL 2026-01-02", "spozywcze", "Biedronka"),
        ("McDonalds 14  Xyz POL 2025-01-29", "restauracje", "McDonald's"),
        ("MCDONALD'S 14 XYZ", "restauracje", "McDonald's"),
        ("AMZN*AB12CD34E5 XYZ LUX", "zakupy-online", "Amazon"),
        ("Amazon Prime*1a2B34CD5 XYZ", "subskrypcje", "Amazon Prime"),
        ("Google Play Apps  Xyz IRL 2026-01-30", "subskrypcje", "Google"),
        ("BOLT.EU/O/1234567890 XYZ", "komunikacja", "Bolt"),
        ("BOLT FOOD XYZ", "dostawy-jedzenia", "Bolt Food"),
        ("www.hm.com (mobile)", "ubrania", "H&M"),
        ("CARREFOUR SUPERMARKET UL. TESTOWA", "spozywcze", "Carrefour"),
        ("APTEKA TESTOWA XYZ POL", "apteka", None),
        ("PIEKARNIA TESTOWA 12 XYZ", "spozywcze", None),
        ("Bankomat Euronet", "wyplaty-gotowki", "Euronet"),
        ("ebok.tauron.pl", "media", "Tauron"),
    ],
)
def test_match(text: str, slug: str, name: str | None) -> None:
    assert (_slug(text), _name(text)) == (slug, name)


@pytest.mark.parametrize(
    "text",
    ["", "Przelew BLIK na telefon", "PLAYGROUND XYZ", "SKLEP ABC XYZ POL 2026-01-02"],
)
def test_no_match(text: str) -> None:
    assert _slug(text) is None


def test_parse_rejects_bad_dictionary() -> None:
    with pytest.raises(DictionaryError, match="version"):
        merchants.parse({})
    with pytest.raises(DictionaryError, match="znormalizowanej"):
        merchants.parse({"version": 1, "keywords": {"apteka": ["apteka"]}})
    with pytest.raises(DictionaryError, match="powtórzony"):
        merchants.parse(
            {"version": 1, "brands": {"spozywcze": {"A": ["LIDL"]}}, "keywords": {"x": ["LIDL"]}}
        )


def test_longest_pattern_then_order() -> None:
    d = merchants.parse(
        {
            "version": 1,
            "brands": {"a": {"Jeden": ["ORLEN"], "Dwa": ["ORLEN PACZKA"]}},
            "keywords": {"b": ["PACZKA"]},
        }
    )
    hit = d.match("ORLEN PACZKA 123")
    assert hit is not None and hit.name == "Dwa"
    hit = d.match("PACZKA ORLEN")  # remis jednego słowa: marka przed słowem ogólnym
    assert hit is not None and hit.name == "Jeden"


@pytest.mark.parametrize(
    ("kind", "description", "counterparty", "source"),
    [
        ("card", "LIDL UL. X XYZ POL 2026-01-02", None, "LIDL UL. X XYZ POL 2026-01-02"),
        ("blik", "/OPT/X///// 123 BRAMKA", "www.sklep.pl", "www.sklep.pl"),
        ("blik", "SKLEP INTERNETOWY", None, "SKLEP INTERNETOWY"),
        ("cash", "", "Bankomat Euronet", "Bankomat Euronet"),
        ("transfer_out", "Netflix za marzec", "JAN KOWALSKI", "JAN KOWALSKI"),
        ("transfer_in", "Netflix", None, ""),
    ],
)
def test_source_text(kind: str, description: str, counterparty: str | None, source: str) -> None:
    assert merchants.source_text(kind, description, counterparty) == source


@pytest.mark.parametrize(
    ("kind", "description", "counterparty", "merchant"),
    [
        ("card", "LA TRATTORIA ROMANA UL. X 1 XYZ POL 2026-01-02", None, "La Trattoria"),
        ("card", "ZABKA Z1234 K.1 UL. X XYZ", None, "Zabka"),
        ("card_refund", "Allegro  Xyz POL 2026-01-29", None, "Allegro"),
        ("blik", "/OPT/X///// 1", "https://www.aliexpress.com/", "aliexpress.com"),
        ("blik", "/OPT/X///// 1", "www.hm.com (mobile)", "hm.com"),
        ("transfer_out", "Czynsz", "JAN  KOWALSKI", "Jan Kowalski"),
        (
            "standing_order",
            "Opłata",
            "Wspólnota Mieszkaniowa Przykładowa",
            "Wspólnota Mieszkaniowa Przykładowa",
        ),
        ("loan", "SPŁATA RATY KREDYTU", None, "Spłata Raty Kredytu"),
    ],
)
def test_base_merchant(
    kind: str, description: str, counterparty: str | None, merchant: str
) -> None:
    assert merchants.base_merchant(kind, description, counterparty) == merchant
