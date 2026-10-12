"""Podział transakcji na podkategorie (M29 E1).

Części (`txn_split`) sumują się co do grosza do kwoty transakcji i liczą się w swoich
podkategoriach we wszystkich wyliczeniach (`spending._rows`). `txn.category_id` = część o
największej kwocie, ze źródłem `manual`, więc ponowna kategoryzacja jej nie rusza.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from budget import money
from budget.categorize import engine, taxonomy
from budget.categorize.taxonomy import TaxonomyError

Part = tuple[int, Decimal]  # (podkategoria, kwota ze znakiem transakcji)


def get(conn: sqlite3.Connection, txn_id: int) -> list[Part]:
    return [
        (int(r["category_id"]), Decimal(r["amount"]))
        for r in conn.execute(
            "SELECT category_id, amount FROM txn_split WHERE txn_id = ? ORDER BY line", (txn_id,)
        )
    ]


def clear(conn: sqlite3.Connection, txn_id: int) -> None:
    """Usuwa podział; kategorię da ponowna kategoryzacja (`engine.recategorize`)."""
    engine.set_manual(conn, txn_id, None)


def _check(conn: sqlite3.Connection, txn_id: int, parts: list[Part]) -> None:
    row = conn.execute("SELECT amount, transfer_group FROM txn WHERE id = ?", (txn_id,)).fetchone()
    if row is None:
        raise TaxonomyError("Nie ma takiej transakcji.")
    if row["transfer_group"] is not None:
        raise TaxonomyError("Przelew między własnymi kontami nie ma kategorii.")
    if len(parts) < 2:
        raise TaxonomyError("Podział wymaga co najmniej dwóch części.")
    leaves = taxonomy.leaves(conn)
    if any(cat not in leaves for cat, _ in parts):
        raise TaxonomyError("Każda część musi mieć podkategorię.")
    if len({cat for cat, _ in parts}) < len(parts):
        raise TaxonomyError("Każda część musi mieć inną podkategorię.")
    amount = Decimal(row["amount"])
    if any(a == 0 or (a < 0) != (amount < 0) for _, a in parts):
        raise TaxonomyError("Każda część musi mieć kwotę ze znakiem transakcji.")
    rest = abs(amount) - sum(abs(a) for _, a in parts)
    if rest > 0:
        raise TaxonomyError(f"Zostało do przydzielenia: {money.pl(rest, 'PLN')}.")
    if rest < 0:
        raise TaxonomyError(f"Przydzielono o {money.pl(-rest, 'PLN')} za dużo.")


def save(conn: sqlite3.Connection, txn_id: int, parts: list[Part], source: str = "manual") -> None:
    _check(conn, txn_id, parts)
    conn.execute("DELETE FROM txn_split WHERE txn_id = ?", (txn_id,))
    conn.executemany(
        "INSERT INTO txn_split (txn_id, line, category_id, amount, source) VALUES (?, ?, ?, ?, ?)",
        [(txn_id, n, cat, str(amount), source) for n, (cat, amount) in enumerate(parts)],
    )
    largest = max(parts, key=lambda p: abs(p[1]))[0]
    conn.execute(
        "UPDATE txn SET category_id = ?, category_source = 'manual', rule_id = NULL WHERE id = ?",
        (largest, txn_id),
    )
