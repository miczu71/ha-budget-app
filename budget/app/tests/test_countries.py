"""Kraj płatności kartą — opisy syntetyczne w formatach Millennium."""

from __future__ import annotations

import pytest

from budget.countries import NAMES, Origin, card_origin, code_from_description


@pytest.mark.parametrize(
    ("description", "code"),
    [
        ("ZABKA Z1234 K.1 UL. TESTOWA 1 XYZ POL 2026-01-02", "POL"),
        ("McDonalds 14  Xyz POL 2025-01-29", "POL"),
        ("SKLEP ABC XyzCHE 2026-09-12", "CHE"),  # kod sklejony z miejscowością
        ('KAWIARNIA TEST Xyz CZE 2026-09-13"', "CZE"),  # cudzysłów z CSV
        ("Google Play Apps  Xyz IRL 2026-01-30", "IRL"),
        ("AMZN*AB12CD34E5 XYZ LUX", "LUX"),  # konto karty: kod na końcu
        ("PIZZERIA TEST SRL XYZ 2026-09-14", None),  # nazwa firmy, nie kraj
        ("SKLEP TEST SPA", None),
        ("SKLEP.COM", None),  # domena, nie Komory
        ("SKLEP ABC UL. XYZ 12 XYZ P 2026-09-15", None),  # opis obcięty przez API
        ("Pizzeria Test 12345", None),
        ("", None),
        (None, None),
    ],
)
def test_code_from_description(description: str | None, code: str | None) -> None:
    assert code_from_description(description) == code


def test_card_origin_country() -> None:
    assert card_origin("card", "SKLEP ABC XYZ CHE 2026-09-12", None) == Origin("CHE", "Szwajcaria")
    assert card_origin("card_refund", "SKLEP ABC XYZ CZE 2026-09-12", None) == Origin(
        "CZE", "Czechy"
    )


def test_card_origin_domestic_and_unknown() -> None:
    assert card_origin("card", "SKLEP XYZ POL 2026-09-12", None) is None
    assert card_origin("card", "SKLEP ABC", None) is None
    assert card_origin("card", "SKLEP ABC", "PLN") is None


def test_card_origin_currency_fallback() -> None:
    assert card_origin("card", "Restaurant Test Xyz", "eur") == Origin(
        "waluta:EUR", "Zagranica (EUR)"
    )
    # kod kraju ma pierwszeństwo przed walutą
    assert card_origin("card", "SKLEP XYZ AUT", "EUR") == Origin("AUT", "Austria")
    # waluta obca przy kodzie domowym nie robi z płatności zagranicznej
    assert card_origin("card", "SKLEP XYZ POL 2026-09-12", "EUR") is None


def test_card_origin_only_cards() -> None:
    assert card_origin("transfer_out", "PRZELEW XYZ CHE 2026-09-12", "EUR") is None
    assert card_origin("blik", "sklep.test XYZ CHE", None) is None


def test_names_iso_alpha3() -> None:
    assert "POL" not in NAMES
    assert all(len(k) == 3 and k.isalpha() and k.isupper() for k in NAMES)
    assert len(NAMES) >= 240
