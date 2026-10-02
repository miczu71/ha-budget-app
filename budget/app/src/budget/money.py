"""Kwoty: wyłącznie `Decimal`, w bazie jako kanoniczny tekst ze znakiem (`-12.30`).

Sumy liczymy w Pythonie — SQLite zamieniłby tekst na float przy `SUM()`.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class AmountError(ValueError):
    pass


def parse(value: str | None) -> Decimal | None:
    """`"-12.3"` → `Decimal("-12.30")`; pusty tekst → `None`. Przecinek dziesiętny dozwolony."""
    if value is None:
        return None
    text = value.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text).quantize(CENT)
    except InvalidOperation as exc:
        raise AmountError(f"niepoprawna kwota: {value!r}") from exc


def signed(debit: str | None, credit: str | None) -> Decimal | None:
    """Kwota ze znakiem z pary kolumn obciążenie/uznanie (obciążenie zawsze ujemne)."""
    d, c = parse(debit), parse(credit)
    if d and c:
        raise AmountError("wypełnione jednocześnie obciążenie i uznanie")
    if d:
        return -abs(d)
    if c is not None:
        return abs(c)
    return None if d is None else ZERO


def fmt(value: Decimal) -> str:
    """Kanoniczny zapis do bazy: dwa miejsca po przecinku, bez `-0.00`."""
    q = value.quantize(CENT)
    return str(q if q else ZERO)


def total(values: Iterable[str | Decimal]) -> Decimal:
    return sum((v if isinstance(v, Decimal) else Decimal(v) for v in values), ZERO)
