import logging

import pytest

from budget.logging_utils import RedactingFilter, mask_iban, redact

IBAN = "PL61109010140000071219812874"


@pytest.mark.parametrize(
    ("iban", "expected"),
    [
        (IBAN, "PL** **** … 2874"),
        ("PL61 1090 1014 0000 0712 1981 2874", "PL** **** … 2874"),
        (None, ""),
        ("", ""),
        ("PL12", "****"),
    ],
)
def test_mask_iban(iban: str | None, expected: str) -> None:
    assert mask_iban(iban) == expected


def test_redact_secrets() -> None:
    jwt = "eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJ4In0.c2lnbmF0dXJl"
    text = (
        f"Authorization: Bearer abc.def.ghi url=https://x/cb?code=SECRET123&state=s1 "
        f"token {jwt} iban {IBAN}"
    )
    out = redact(text)
    assert "abc.def.ghi" not in out
    assert "SECRET123" not in out
    assert jwt not in out
    assert IBAN not in out
    assert "PL** **** … 2874" in out
    assert "state=s1" in out


def test_filter_applies_to_args(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("test.redact")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO, logger="test.redact"):
        logger.info("konto %s", IBAN)
    assert IBAN not in caplog.text
    assert "2874" in caplog.text
