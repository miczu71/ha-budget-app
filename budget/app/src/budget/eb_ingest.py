"""Transakcje z Enable Banking → wspólny model księgi (odcisk, numer wystąpienia, typ)."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from budget import money
from budget.eb_models import Transaction
from budget.kinds import Kind, from_api
from budget.normalize import card_desc_date, desc_key


def fingerprint(booking_date: date, amount: Decimal, description: str) -> str:
    """Odcisk transakcji w obrębie konta: (data, kwota, opis znormalizowany)."""
    key = f"{booking_date.isoformat()}|{money.fmt(amount)}|{desc_key(description)}"
    return hashlib.sha256(key.encode()).hexdigest()[:20]


@dataclass(frozen=True)
class ApiTxn:
    refs: tuple[tuple[str, str], ...]  # (źródło, referencja): eb_entry / eb_txid
    status: str
    booking_date: date
    value_date: date | None
    tx_date: date | None
    amount: Decimal
    currency: str
    description: str
    counterparty_name: str | None
    counterparty_account: str | None
    kind: Kind
    fingerprint: str
    occurrence: int
    raw: dict[str, Any]


def _ref_order(t: Transaction) -> tuple[int, str]:
    """Kolejność w obrębie dnia: licznik z końca `entry_reference` (`BOOKED|…|data|3`)."""
    ref = t.entry_reference or t.transaction_id or ""
    tail = ref.rsplit("|", 1)[-1]
    return (int(tail), "") if tail.isdigit() else (0, ref)


def convert(txns: Sequence[Transaction], *, card_account: bool) -> list[ApiTxn]:
    """Konwersja jednej odpowiedzi API (całe okno jednego konta).

    Numer wystąpienia rozróżnia identyczne transakcje z tego samego dnia (dwa takie same
    zakupy) — razem z odciskiem identyfikuje transakcję, gdy bank przenumeruje referencję.
    """
    dated = []
    for t in txns:
        booking = t.booking_date or t.transaction_date or t.value_date
        if booking is None:
            continue  # bez żadnej daty nie da się jej umieścić w księdze
        dated.append((booking, t))
    dated.sort(key=lambda bt: (bt[0], bt[1].status, _ref_order(bt[1])))

    seen: dict[str, int] = defaultdict(int)
    out = []
    for booking, t in dated:
        amount = t.signed_amount
        description = t.description
        fp = fingerprint(booking, amount, description)
        occurrence = seen[fp]
        seen[fp] += 1
        refs = tuple(
            (source, ref)
            for source, ref in (("eb_entry", t.entry_reference), ("eb_txid", t.transaction_id))
            if ref
        )
        tx_date = t.transaction_date
        if tx_date is None and (from_desc := card_desc_date(description)):
            tx_date = date.fromisoformat(from_desc)
        out.append(
            ApiTxn(
                refs=refs,
                status="PDNG" if t.status == "PDNG" else "BOOK",
                booking_date=booking,
                value_date=t.value_date,
                tx_date=tx_date,
                amount=amount,
                currency=t.transaction_amount.currency,
                description=description,
                counterparty_name=t.counterparty_name,
                counterparty_account=t.counterparty_iban,
                kind=from_api(
                    description,
                    amount,
                    card_account=card_account,
                    counterparty_name=t.counterparty_name,
                    counterparty_account=t.counterparty_iban,
                ),
                fingerprint=fp,
                occurrence=occurrence,
                raw=t.raw,
            )
        )
    return out


_DUMP_RE = re.compile(r"^transactions_(\d+)_([0-9a-f]{8})_(\d{8}T\d{6}Z)\.json$")


@dataclass(frozen=True)
class Dump:
    path: Path
    account_index: int
    hash_digest: str  # sha256(identification_hash)[:8] — jak w `cli transactions`
    fetched_at: str  # ISO, z nazwy pliku
    date_from: date | None
    transactions: list[Transaction]


def hash_digest(identification_hash: str) -> str:
    return hashlib.sha256(identification_hash.encode()).hexdigest()[:8]


def load_dump(path: Path) -> Dump | None:
    """Zrzut z `cli transactions`; inne pliki (np. sondy) → `None`."""
    m = _DUMP_RE.match(path.name)
    if not m:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    stamp = m.group(3)
    fetched_at = (
        f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}+00:00"
    )
    date_from = data.get("date_from")
    return Dump(
        path=path,
        account_index=int(m.group(1)),
        hash_digest=m.group(2),
        fetched_at=fetched_at,
        date_from=date.fromisoformat(date_from) if date_from else None,
        transactions=[Transaction.from_api(t) for t in data.get("transactions", [])],
    )
