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
