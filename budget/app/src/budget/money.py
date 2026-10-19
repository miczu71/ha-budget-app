"""Kwoty: wyłącznie `Decimal`, w bazie jako kanoniczny tekst ze znakiem (`-12.30`).

Sumy liczymy w Pythonie — SQLite zamieniłby tekst na float przy `SUM()`.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

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
        amount = Decimal(text)
        if not amount.is_finite():
            raise InvalidOperation
        return amount.quantize(CENT)
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


def pl(value: Any, currency: str | None = None, *, whole: bool = False) -> str:
    """`-1234.5` → `−1 234,50 zł` (polski zapis, twarde spacje); `whole` — pełne złote."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return "—"
    sign = "−" if amount < 0 else ""
    shown = abs(amount).quantize(Decimal(1), ROUND_HALF_UP) if whole else abs(amount)
    digits, _, frac = f"{shown:.{0 if whole else 2}f}".partition(".")
    groups: list[str] = []
    while digits:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    symbol = {"PLN": "zł", "EUR": "€", None: ""}.get(currency, currency or "")
    # grupy cyfr: wąska twarda spacja (U+202F), przed walutą: twarda spacja (U+00A0)
    cents = "" if whole else f",{frac}"
    return f"{sign}{'\u202f'.join(groups)}{cents}\xa0{symbol}".rstrip()
