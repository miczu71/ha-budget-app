from budget.normalize import (
    card_desc_date,
    desc_key,
    fold,
    merchant_key,
    same_merchant,
)


def test_fold_strips_diacritics_and_nbsp() -> None:
    assert fold("Płatność\xa0kartą  w   internecie") == "PLATNOSC KARTA W INTERNECIE"
    assert fold(None) == ""


def test_desc_key_ignores_cut_points() -> None:
    # API wstawia spację w miejscu cięcia linii, CSV — twardą spację
    api = "SKLEP TESTOWY UL. TESTOWA 1 Przykl adowo POL 2026-09-30"
    csv = "SKLEP TESTOWY UL. TESTOWA 1 Przyk\xa0ladowo POL 2026-09-30"
    assert desc_key(api) == desc_key(csv)


def test_card_desc_date() -> None:
    assert card_desc_date("LIDL UL. TESTOWA 5 TESTOWO POL 2026-09-29") == "2026-09-29"
    assert card_desc_date("Przelew własny") is None


def test_merchant_key() -> None:
    assert merchant_key("ZABKA Z1234 K.2 UL. TESTOWA TESTOWO POL 2026-09-29") == "ZABKA"
    assert merchant_key("AMZN*AB12CD34 1 Avenue Test Luxembourg LUX 2026-09-29", 1) == "AMZN"
    assert merchant_key("/OPT/X///// BPID:AB12 T-K1 Autopay S.A.", 1) == "BPID"
    assert merchant_key("SKLEP TESTOWY 025        , TESTOWO 4    , 616") == "SKLEP TESTOWY"
    assert merchant_key("Zalando Payments GmbH    ") == "ZALANDO PAYMENTS"


def test_same_merchant() -> None:
    assert same_merchant("ZALANDO SE Berlin DEU 2026-09-01", "Zalando Payments GmbH")
    assert not same_merchant("ZALANDO SE", "LIDL")
    assert not same_merchant("", "")


def test_same_merchant_domain_vs_name() -> None:
    assert same_merchant("www.zalando.pl", "ZALANDO SE TESTOWO DEU 2026-09-01")
    assert merchant_key("P4 Sp. z o.o. testowa 1 testowo POL 2026-09-28", 1) == "P4"


def test_number_after_name_ends_merchant() -> None:
    # CSV karty dokleja miasto, API ma tylko „nazwa numer stacji”
    assert same_merchant("Eko 1005 Testowo", "Eko 1005")
    assert merchant_key("7-ELEVEN 123 TESTOWO") == "7-ELEVEN"


def test_search_words_and_matches_all() -> None:
    from budget.normalize import matches_all, search_words

    assert search_words("  Żółw   czynsz ") == ["ZOLW", "CZYNSZ"]
    assert search_words("") == [] and search_words(None) == []
    haystack = fold("Czynsz za miesiąc — Spółdzielnia Qwęrtóś")
    assert matches_all(haystack, search_words("czyn MIES"))
    assert matches_all(haystack, search_words("qwertos spoldz"))  # bez ogonków, dowolna kolejność
    assert not matches_all(haystack, search_words("czynsz prąd"))
    assert matches_all(haystack, [])  # puste zapytanie pasuje do wszystkiego
