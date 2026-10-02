from decimal import Decimal

import pytest

from budget import money


def test_parse_quantizes_and_accepts_comma() -> None:
    assert money.parse("-12.3") == Decimal("-12.30")
    assert money.parse(" 1\xa0234,5 ") == Decimal("1234.50")
    assert money.parse("") is None
    assert money.parse(None) is None


def test_parse_rejects_garbage() -> None:
    with pytest.raises(money.AmountError):
        money.parse("12,34,56")


@pytest.mark.parametrize(
    ("debit", "credit", "expected"),
    [
        ("-12.34", "", Decimal("-12.34")),
        ("12.34", "", Decimal("-12.34")),  # obciążenie zawsze ujemne
        ("", "5.27", Decimal("5.27")),
        ("", "", None),
    ],
)
def test_signed(debit: str, credit: str, expected: Decimal | None) -> None:
    assert money.signed(debit, credit) == expected


def test_signed_both_filled_is_error() -> None:
    with pytest.raises(money.AmountError):
        money.signed("-1.00", "1.00")


def test_fmt_and_total() -> None:
    assert money.fmt(Decimal("-0.001")) == "0.00"
    assert money.fmt(Decimal("100.0")) == "100.00"
    assert money.total(["0.10", "0.20", Decimal("-0.30")]) == Decimal("0.00")
