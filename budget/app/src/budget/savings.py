"""Konto oszczędnościowe poza Enable Banking (M10 E2, decyzja 26).

Saldo = saldo wpisane na dzień + przelewy z rachunków w księdze na numer konta (wpłata) i z niego
(wypłata) po tej dacie. Przelewy na konto nie liczą się do puli Flex (`snapshot.piggy_ids`).
Numer konta tylko w bazie, w panelu maskowany. Odsetki i promocja — E3, stopa oszczędności — E4.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from budget import money, piggy
from budget.logging_utils import mask_iban
from budget.piggy import PiggyError
from budget.storage.db import now_iso

ZERO = money.ZERO


class SavingsError(PiggyError):
    pass


@dataclass(frozen=True)
class Account:
    id: int
    name: str
    account_number: str
    opening_balance: Decimal
    opening_date: date

    @property
    def masked(self) -> str:
        return mask_iban("PL" + self.account_number)


def _row(r: sqlite3.Row) -> Account:
    return Account(
        id=r["id"],
        name=r["name"],
        account_number=r["account_number"],
        opening_balance=Decimal(r["opening_balance"]),
        opening_date=date.fromisoformat(r["opening_date"]),
    )


def all_accounts(conn: sqlite3.Connection) -> list[Account]:
    return [
        _row(r)
        for r in conn.execute(
            "SELECT * FROM savings_account WHERE archived_at IS NULL ORDER BY name"
        )
    ]


def get(conn: sqlite3.Connection, account_id: int) -> Account:
    row = conn.execute("SELECT * FROM savings_account WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise SavingsError("Nie ma takiego konta oszczędnościowego.")
    return _row(row)


def save(
    conn: sqlite3.Connection,
    *,
    account_id: int | None,
    name: str,
    account_number: str,
    opening_balance: str | None,
    opening_date: str | None,
) -> int:
    """Nowe konto (`account_id` None) albo zmiana (pusty numer = bez zmiany — panel pokazuje go
    zamaskowany). Nowe saldo na nowy dzień to korekta względem banku."""
    clean = " ".join(name.split())[:40]
    if not clean:
        raise SavingsError("Podaj nazwę konta.")
    if account_id is not None and not account_number.strip():
        number = get(conn, account_id).account_number
    else:
        number = piggy.normalize_number(account_number)
    try:
        day = date.fromisoformat(opening_date or "")
    except ValueError as exc:
        raise SavingsError("Podaj datę salda.") from exc
    opening = piggy._amount(opening_balance, "saldo konta", allow_zero=True) or ZERO
    params = (clean, number, str(opening), day.isoformat())
    try:
        if account_id is None:
            cur = conn.execute(
                "INSERT INTO savings_account (name, account_number, opening_balance, "
                "opening_date, created_at) VALUES (?, ?, ?, ?, ?)",
                (*params, now_iso()),
            )
            return int(cur.lastrowid or 0)
        cur = conn.execute(
            "UPDATE savings_account SET name = ?, account_number = ?, opening_balance = ?, "
            "opening_date = ? WHERE id = ?",
            (*params, account_id),
        )
    except sqlite3.IntegrityError as exc:
        raise SavingsError("Konto o tej nazwie albo tym numerze już jest.") from exc
    if not cur.rowcount:
        raise SavingsError("Nie ma takiego konta oszczędnościowego.")
    return account_id


def archive(conn: sqlite3.Connection, account_id: int) -> None:
    cur = conn.execute(
        "UPDATE savings_account SET archived_at = ? WHERE id = ?", (now_iso(), account_id)
    )
    if not cur.rowcount:
        raise SavingsError("Nie ma takiego konta oszczędnościowego.")


def movements(conn: sqlite3.Connection, acc: Account) -> list[sqlite3.Row]:
    """Przelewy po dacie salda: `id`, `day`, `amount` ze znakiem rachunku (ujemny = wpłata)."""
    return [
        r
        for r in piggy.transfers(conn, [acc.account_number])
        if date.fromisoformat(r["day"]) > acc.opening_date
    ]


def balance(conn: sqlite3.Connection, acc: Account) -> Decimal:
    return acc.opening_balance - sum((Decimal(r["amount"]) for r in movements(conn, acc)), ZERO)


def txn_ids(conn: sqlite3.Connection) -> set[int]:
    """Przelewy na konta oszczędnościowe i z nich (poza pulą Flex — cała historia, nie tylko
    po dacie salda)."""
    numbers = [r[0] for r in conn.execute("SELECT account_number FROM savings_account")]
    return {r["id"] for r in piggy.transfers(conn, numbers)}
