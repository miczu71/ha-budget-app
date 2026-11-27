"""Opis karty z Velobanku: sprzedawca stoi po „… na kwotę X PLN w ”."""

from budget.categorize.merchants import base_merchant
from budget.normalize import merchant_ident, same_merchant
from budget.suggest.redact import scrub

PREFIX = "Operacja kartą 0000 xxxx xxxx 0000 na kwotę 10,00 PLN w "
SHOP = PREFIX + "SKLEPIK 12 KASA 1, MIASTO A, POL"
OTHER_SHOP = PREFIX + "PIEKARNIA, MIASTO A, POL"


def test_merchant_is_the_shop_not_the_operation() -> None:
    assert merchant_ident(SHOP) == "SKLEPIK"
    assert base_merchant("card", SHOP, "SKLEPIK 12 KASA 1") == "Sklepik"


def test_different_shops_are_not_the_same_merchant() -> None:
    assert not same_merchant(SHOP, OTHER_SHOP)
    assert same_merchant(SHOP, PREFIX + "SKLEPIK 34, MIASTO B, POL")


def test_scrub_drops_card_number_prefix() -> None:
    assert scrub(OTHER_SHOP) == "PIEKARNIA, MIASTO A, POL"
