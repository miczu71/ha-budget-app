"""Parser eksportu „Historia transakcji” z Millenetu (format: `docs/FINDINGS_millenet_csv.md`).

Tylko parsowanie i kontrole na poziomie pliku — łączenie z księgą robi `ledger`.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from itertools import pairwise

from budget import money
from budget.kinds import Kind, from_csv
from budget.normalize import NBSP, fold

ACCOUNT = "Numer rachunku/karty"
TX_DATE = "Data transakcji"
SETTLE_DATE = "Data rozliczenia"
KIND = "Rodzaj transakcji"
OTHER_ACC = "Na konto/Z konta"
PARTY = "Odbiorca/Zleceniodawca"
DESC = "Opis"
DEBIT = "Obciążenia"
CREDIT = "Uznania"
BALANCE = "Saldo"
CURRENCY = "Waluta"
COLUMNS = (
    ACCOUNT,
    TX_DATE,
    SETTLE_DATE,
    KIND,
    OTHER_ACC,
    PARTY,
    DESC,
    DEBIT,
    CREDIT,
    BALANCE,
    CURRENCY,
)

WRAP = 45  # Millenet zawija opis twardą spacją co 45 znaków
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ORIG_RE = re.compile(r"(-?\d+(?:\.\d+)?) ([A-Z]{3})$")


class CsvFormatError(ValueError):
    pass


@dataclass(frozen=True)
class CsvRow:
    line: int  # numer linii w pliku (1 = nagłówek), kolejność: od najnowszych
    number: str  # numer rachunku (IBAN bez spacji) albo zamaskowany numer karty
    is_card: bool
    tx_date: date
    settle_date: date
    kind_raw: str
    kind: Kind
    amount: Decimal
    currency: str
    balance_after: Decimal | None
    description: str
    counterparty_name: str | None
    counterparty_account: str | None
    orig_amount: Decimal | None = None
    orig_currency: str | None = None
    occurrence: int = 0  # numer kolejny identycznego wiersza (bliźniaki) — ustawia `collapse`

    @property
    def signature(self) -> tuple[date, date, Decimal, str]:
        """Tożsamość wiersza w obrębie konta (bez numeru karty i numeru linii)."""
        return (self.tx_date, self.settle_date, self.amount, fold(self.description))


@dataclass
class ParseResult:
    rows: list[CsvRow] = field(default_factory=list)
    skipped: list[tuple[int, str]] = field(default_factory=list)  # (linia, powód)


def unwrap(text: str) -> str:
    """Odwraca zawijanie: segment 44-znakowy zjadł spację, 45-znakowy — nic."""
    parts = text.split(NBSP)
    out = ""
    for part in parts[:-1]:
        out += part + (" " if len(part) == WRAP - 1 else "")
    return out + parts[-1]


def _account_description(raw: str) -> str:
    """Opis z rachunku; płatność kartą kończy się `⍽RRRR-MM-DD` — data zostaje jako słowo,
    jak w API (`… POL 2026-09-30`)."""
    parts = raw.split(NBSP)
    if len(parts) > 1 and _DATE_RE.fullmatch(parts[-1]):
        return f"{unwrap(NBSP.join(parts[:-1]))} {parts[-1]}"
    return unwrap(raw)


def _card_description(raw: str) -> tuple[str, Decimal | None, str | None]:
    """Opis z eksportu karty: `SPRZEDAWCA(25), MIASTO(14), kraj [kwota waluta]`."""
    fields = [f.strip() for f in raw.split(",")]
    orig_amount = orig_currency = None
    if fields and (m := _ORIG_RE.search(fields[-1])):
        orig_amount, orig_currency = money.parse(m.group(1)), m.group(2)
        fields[-1] = fields[-1][: m.start()].strip()
    # Sprzedawca + miasto; krótszy opis (np. opłata banku) — tylko pierwsze pole
    text = " ".join(fields[:2]) if len(fields) >= 3 else fields[0]
    return re.sub(r"\s+", " ", text), orig_amount, orig_currency


def _number(value: str) -> tuple[str, bool]:
    compact = value.replace(" ", "").upper()
    is_card = len(re.sub(r"\D", "", compact)) != 26
    return compact, is_card


def parse(data: bytes) -> ParseResult:
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise CsvFormatError(f"to nie jest eksport Millenetu — brak kolumn: {missing}")
    result = ParseResult()
    for row in reader:
        line = reader.line_num
        try:
            amount = money.signed(row[DEBIT], row[CREDIT])
        except money.AmountError as exc:
            result.skipped.append((line, str(exc)))
            continue
        if amount is None:
            result.skipped.append((line, "brak kwoty"))
            continue
        number, is_card = _number(row[ACCOUNT])
        orig_amount = orig_currency = None
        if is_card:
            description, orig_amount, orig_currency = _card_description(row[DESC])
        else:
            description = _account_description(row[DESC])
        party = row[PARTY].split(NBSP)[0].strip() or None
        other = row[OTHER_ACC].replace(" ", "") or None
        try:
            tx_date = date.fromisoformat(row[TX_DATE])
            settle_date = date.fromisoformat(row[SETTLE_DATE])
        except ValueError:
            result.skipped.append((line, "niepoprawna data"))
            continue
        result.rows.append(
            CsvRow(
                line=line,
                number=number,
                is_card=is_card,
                tx_date=tx_date,
                settle_date=settle_date,
                kind_raw=row[KIND].strip(),
                kind=from_csv(row[KIND], amount, card_account=is_card, description=description),
                amount=amount,
                currency=row[CURRENCY].strip() or "PLN",
                balance_after=money.parse(row[BALANCE]),
                description=description,
                counterparty_name=party,
                counterparty_account=f"PL{other}" if other and other.isdigit() else other,
                orig_amount=orig_amount,
                orig_currency=orig_currency,
            )
        )
    return result


def collapse(rows_by_number: dict[str, Sequence[CsvRow]]) -> list[CsvRow]:
    """L0: wiersze jednego konta spod kilku numerów (karta główna + dodatkowa).

    Ta sama transakcja pod dwoma numerami liczy się raz; prawdziwe bliźniaki (dwa identyczne
    zakupy) zostają — dla każdego odcisku bierzemy max(liczności), nie sumę. Każdy wynikowy
    wiersz dostaje `occurrence` (0, 1, …) w obrębie swojego odcisku.
    """
    best: dict[tuple[date, date, Decimal, str], list[CsvRow]] = {}
    for number in sorted(rows_by_number):
        groups: dict[tuple[date, date, Decimal, str], list[CsvRow]] = defaultdict(list)
        for row in rows_by_number[number]:
            groups[row.signature].append(row)
        for sig, group in groups.items():
            if len(group) > len(best.get(sig, [])):
                best[sig] = group
    out = [
        replace(row, occurrence=i)
        for group in best.values()
        for i, row in enumerate(sorted(group, key=lambda r: r.line))
    ]
    return sorted(out, key=lambda r: r.line)


def balance_breaks(rows: Iterable[CsvRow]) -> list[tuple[int, Decimal]]:
    """Przerwy ciągłości salda rachunku: (linia nowszego wiersza, rozbieżność).

    Wiersze są od najnowszych: saldo starszego + kwota nowszego = saldo nowszego.
    """
    ordered = sorted(
        (r.line, r.amount, r.balance_after) for r in rows if r.balance_after is not None
    )
    breaks = []
    for (line, amount, balance), (_, _, older_balance) in pairwise(ordered):
        if diff := older_balance + amount - balance:
            breaks.append((line, diff))
    return breaks


def numbers(rows: Iterable[CsvRow]) -> Counter[str]:
    return Counter(r.number for r in rows)
