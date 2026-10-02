"""Księga: wczytywanie API i CSV do jednej bazy bez duplikatów (plan: `docs/PLAN_M2.md`).

Warstwy deduplikacji:
- L0 w obrębie źródła — API: referencja, potem odcisk + numer wystąpienia; CSV: ta sama
  transakcja pod numerem karty głównej i dodatkowej liczy się raz (`csv_import.collapse`).
- L1 CSV↔API — przed najstarszą transakcją API konta wiersze CSV są transakcjami; w oknie
  API tylko wzbogacają transakcję z API (typ, konto kontrahenta, waluta oryginalna, saldo).
- L2 przelewy między podlinkowanymi kontami (spłata karty) — `transfer_group`.
- L3 zwroty → zakup (`refund_of`).
- L4 PDNG→BOOK — oczekujące są zastępowane przy każdym pobraniu.

Powiązania CSV (`relink_csv`), L2/L3 (`rebuild_links`) i kategorie (`categorize.engine`) są
przeliczane od zera po każdym imporcie (`rebuild_derived`), więc kolejność importów jest
obojętna, a ponowny import niczego nie zmienia.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from budget import csv_import, money
from budget.categorize import engine as categorize
from budget.csv_import import CsvRow
from budget.eb_ingest import ApiTxn, fingerprint
from budget.eb_models import Account, Balance
from budget.kinds import PURCHASE_KINDS, REFUND_KINDS, Kind
from budget.normalize import card_desc_date, fold, same_merchant
from budget.storage.db import now_iso

TRANSFER_WINDOW = timedelta(days=3)
REFUND_WINDOW = timedelta(days=90)
FUZZY_DAYS = 5
FUZZY_SHARE = Decimal("0.05")
CARD_MAP_MIN_MATCHES = 3
_CARD_PRODUCT_RE = re.compile(r"VISA|MASTERCARD|MAESTRO|KARTA|CARD")


@dataclass
class ImportStats:
    total: int = 0
    new: int = 0
    updated: int = 0
    skipped: list[tuple[int, str]] = field(default_factory=list)


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    conn.execute("BEGIN")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


# --- konta ---------------------------------------------------------------------------------


def _account_kind(product: str | None, name: str | None, currency: str) -> str:
    if _CARD_PRODUCT_RE.search(fold(f"{product or ''} {name or ''}")):
        return "card"
    return "current" if currency == "PLN" else "fx"


def upsert_eb_account(conn: sqlite3.Connection, acc: Account) -> int:
    """Konto z sesji EB: po aliasie uid, potem po IBAN-ie; aliasy dopisywane."""
    row = conn.execute(
        "SELECT account_id FROM account_alias WHERE source = 'eb_uid' AND value = ?", (acc.uid,)
    ).fetchone()
    if row is None and acc.iban:
        row = conn.execute(
            "SELECT id AS account_id FROM account WHERE iban = ?", (acc.iban,)
        ).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO account (kind, iban, currency, product, display_name, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                _account_kind(acc.product, acc.name, acc.currency),
                acc.iban,
                acc.currency,
                acc.product,
                acc.product or acc.name,
                now_iso(),
            ),
        )
        account_id = int(cur.lastrowid or 0)
    else:
        account_id = int(row["account_id"])
        conn.execute(
            "UPDATE account SET product = coalesce(product, ?) WHERE id = ?",
            (acc.product, account_id),
        )
    for source, value in (("eb_uid", acc.uid), ("eb_hash", acc.identification_hash)):
        conn.execute(
            "INSERT OR IGNORE INTO account_alias (source, value, account_id) VALUES (?, ?, ?)",
            (source, value, account_id),
        )
    return account_id


def account_by_alias(conn: sqlite3.Connection, source: str, value: str) -> int | None:
    row = conn.execute(
        "SELECT account_id FROM account_alias WHERE source = ? AND value = ?", (source, value)
    ).fetchone()
    return int(row["account_id"]) if row else None


def map_csv_number(conn: sqlite3.Connection, number: str, account_id: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO account_alias (source, value, account_id) "
        "VALUES ('csv_number', ?, ?)",
        (number, account_id),
    )


def _is_iban(number: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{2}\d{26}", number))


def _csv_account(conn: sqlite3.Connection, number: str, currency: str) -> int | None:
    """Konto dla numeru z CSV: alias, IBAN (zakładane, gdy brak), karta — `None`."""
    if (account_id := account_by_alias(conn, "csv_number", number)) is not None:
        return account_id
    if not _is_iban(number):
        return None
    row = conn.execute("SELECT id FROM account WHERE iban = ?", (number,)).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO account (kind, iban, currency, created_at) VALUES (?, ?, ?, ?)",
            ("current" if currency == "PLN" else "fx", number, currency, now_iso()),
        )
        account_id = int(cur.lastrowid or 0)
    else:
        account_id = int(row["id"])
    map_csv_number(conn, number, account_id)
    return account_id


def auto_map_card_numbers(conn: sqlite3.Connection) -> dict[str, int]:
    """Numer karty z CSV → konto karty z API, gdy ≥ 3 transakcje zgadzają się (data
    rozliczenia = data księgowania, kwota) i wskazanie jest jednoznaczne."""
    mapped: dict[str, int] = {}
    numbers = [
        r["number"]
        for r in conn.execute(
            "SELECT DISTINCT number FROM csv_row WHERE number NOT IN "
            "(SELECT value FROM account_alias WHERE source = 'csv_number')"
        )
    ]
    cards = [r["id"] for r in conn.execute("SELECT id FROM account WHERE kind = 'card'")]
    for number in numbers:
        if _is_iban(number):
            continue
        keys = {
            (r["settle_date"], r["amount"])
            for r in conn.execute(
                "SELECT settle_date, amount FROM csv_row WHERE number = ?", (number,)
            )
        }
        scores = {}
        for account_id in cards:
            api = {
                (r["booking_date"], r["amount"])
                for r in conn.execute(
                    "SELECT booking_date, amount FROM txn WHERE account_id = ? AND source = 'eb'",
                    (account_id,),
                )
            }
            scores[account_id] = len(keys & api)
        good = [a for a, s in scores.items() if s >= CARD_MAP_MIN_MATCHES]
        if len(good) == 1:
            map_csv_number(conn, number, good[0])
            mapped[number] = good[0]
    return mapped


# --- import API ------------------------------------------------------------------------------


def _new_batch(
    conn: sqlite3.Connection,
    source: str,
    *,
    account_id: int | None = None,
    file_name: str | None = None,
    fetched_at: str,
    date_from: date | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO import_batch (source, account_id, file_name, fetched_at, date_from, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            source,
            account_id,
            file_name,
            fetched_at,
            date_from.isoformat() if date_from else None,
            now_iso(),
        ),
    )
    return int(cur.lastrowid or 0)


def _finish_batch(conn: sqlite3.Connection, batch_id: int, stats: ImportStats) -> None:
    conn.execute(
        "UPDATE import_batch SET rows_total = ?, rows_new = ?, rows_updated = ? WHERE id = ?",
        (stats.total, stats.new, stats.updated, batch_id),
    )


def _update_changed(
    conn: sqlite3.Connection, txn_id: int, current: sqlite3.Row, values: dict[str, Any]
) -> bool:
    """UPDATE tylko zmienionych kolumn; zwraca, czy coś się zmieniło."""
    changed = {k: v for k, v in values.items() if current[k] != v}
    if not changed:
        return False
    sets = ", ".join(f"{k} = ?" for k in changed)
    conn.execute(
        f"UPDATE txn SET {sets}, updated_at = ? WHERE id = ?",
        (*changed.values(), now_iso(), txn_id),
    )
    return True


def _api_values(t: ApiTxn) -> dict[str, Any]:
    return {
        "status": t.status,
        "booking_date": t.booking_date.isoformat(),
        "value_date": t.value_date.isoformat() if t.value_date else None,
        "amount": money.fmt(t.amount),
        "currency": t.currency,
        "description": t.description,
        "fingerprint": t.fingerprint,
        "occurrence": t.occurrence,
        "raw_json": json.dumps(t.raw, ensure_ascii=False, sort_keys=True),
    }


def ingest_api(
    conn: sqlite3.Connection,
    account_id: int,
    txns: Sequence[ApiTxn],
    *,
    fetched_at: str,
    date_from: date | None = None,
    file_name: str | None = None,
) -> ImportStats:
    """Jedna odpowiedź API (okno jednego konta). Dopasowanie: referencja → odcisk +
    wystąpienie (przenumerowana referencja dochodzi jako alias) → nowa transakcja."""
    stats = ImportStats(total=len(txns))
    with transaction(conn):
        batch_id = _new_batch(
            conn,
            "eb",
            account_id=account_id,
            file_name=file_name,
            fetched_at=fetched_at,
            date_from=date_from,
        )
        # L4: oczekujące nie mają stabilnych referencji — zastępujemy je stanem z tego pobrania
        # (nie liczą się do statystyk — inaczej ponowny import zawsze „coś zmieniał”)
        conn.execute(
            "DELETE FROM txn WHERE account_id = ? AND status = 'PDNG' AND source = 'eb'",
            (account_id,),
        )
        for t in txns:
            if t.status == "PDNG":
                _insert_api(conn, account_id, t, batch_id)
                continue
            existing = _find_api_txn(conn, account_id, t)
            if existing is None:
                _insert_api(conn, account_id, t, batch_id)
                stats.new += 1
                continue
            values = _api_values(t)
            if existing["kind_source"] == "heuristic":
                values["kind"] = t.kind.value
            changed = _update_changed(conn, existing["id"], existing, values)
            for source, ref in t.refs:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO txn_ref (account_id, source, ref, txn_id, batch_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (account_id, source, ref, existing["id"], batch_id),
                )
                changed |= cur.rowcount > 0
            stats.updated += changed
        _finish_batch(conn, batch_id, stats)
        rebuild_derived(conn)
    return stats


def _find_api_txn(conn: sqlite3.Connection, account_id: int, t: ApiTxn) -> sqlite3.Row | None:
    for source, ref in t.refs:
        row: sqlite3.Row | None = conn.execute(
            "SELECT txn.* FROM txn_ref JOIN txn ON txn.id = txn_ref.txn_id "
            "WHERE txn_ref.account_id = ? AND txn_ref.source = ? AND txn_ref.ref = ?",
            (account_id, source, ref),
        ).fetchone()
        if row is not None:
            return row
    # Przenumerowana referencja: ta sama transakcja (odcisk + wystąpienie), stara referencja
    found: sqlite3.Row | None = conn.execute(
        "SELECT * FROM txn WHERE account_id = ? AND source = 'eb' AND status = 'BOOK' "
        "AND fingerprint = ? AND occurrence = ?",
        (account_id, t.fingerprint, t.occurrence),
    ).fetchone()
    return found


def _insert_api(conn: sqlite3.Connection, account_id: int, t: ApiTxn, batch_id: int) -> int:
    values = _api_values(t)
    now = now_iso()
    cur = conn.execute(
        "INSERT INTO txn (account_id, status, booking_date, value_date, tx_date, amount, "
        "currency, description, counterparty_name, counterparty_account, kind, kind_source, "
        "fingerprint, occurrence, source, raw_json, first_seen_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'heuristic', ?, ?, 'eb', ?, ?, ?)",
        (
            account_id,
            values["status"],
            values["booking_date"],
            values["value_date"],
            t.tx_date.isoformat() if t.tx_date else None,
            values["amount"],
            values["currency"],
            values["description"],
            t.counterparty_name,
            t.counterparty_account,
            t.kind.value,
            values["fingerprint"],
            values["occurrence"],
            values["raw_json"],
            now,
            now,
        ),
    )
    txn_id = int(cur.lastrowid or 0)
    for source, ref in t.refs:
        conn.execute(
            "INSERT OR IGNORE INTO txn_ref (account_id, source, ref, txn_id, batch_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (account_id, source, ref, txn_id, batch_id),
        )
    return txn_id


def ingest_balances(
    conn: sqlite3.Connection, account_id: int, balances: Iterable[Balance], *, fetched_at: str
) -> int:
    added = 0
    with transaction(conn):
        for b in balances:
            cur = conn.execute(
                "INSERT OR IGNORE INTO balance_snapshot (account_id, balance_type, amount, "
                "currency, reference_date, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    account_id,
                    b.balance_type,
                    money.fmt(b.balance_amount.amount),
                    b.balance_amount.currency,
                    b.reference_date.isoformat() if b.reference_date else None,
                    fetched_at,
                ),
            )
            added += cur.rowcount
    return added


# --- import CSV ------------------------------------------------------------------------------


def _row_key(row: CsvRow, occurrence: int) -> str:
    tx_date, settle, amount, desc = row.signature
    raw = f"{tx_date}|{settle}|{money.fmt(amount)}|{desc}"
    return f"{hashlib.sha256(raw.encode()).hexdigest()[:20]}:{occurrence}"


def ingest_csv(
    conn: sqlite3.Connection,
    data: bytes,
    *,
    file_name: str | None = None,
    fetched_at: str | None = None,
    card_map: dict[str, int] | None = None,
) -> ImportStats:
    """Eksport z Millenetu. Wiersze trafiają do `csv_row` (idempotentnie po odcisku
    i numerze wystąpienia w obrębie numeru), księgę wylicza `relink_csv`."""
    parsed = csv_import.parse(data)
    stats = ImportStats(total=len(parsed.rows), skipped=parsed.skipped)
    with transaction(conn):
        batch_id = _new_batch(conn, "csv", file_name=file_name, fetched_at=fetched_at or now_iso())
        for number, account_id in (card_map or {}).items():
            map_csv_number(conn, number.replace(" ", "").upper(), account_id)
        seen: Counter[tuple[str, tuple[date, date, Decimal, str]]] = Counter()
        for row in sorted(parsed.rows, key=lambda r: r.line):
            _csv_account(conn, row.number, row.currency)  # rachunki zakładane od razu
            occurrence = seen[(row.number, row.signature)]
            seen[(row.number, row.signature)] += 1
            cur = conn.execute(
                "INSERT OR IGNORE INTO csv_row (number, row_key, tx_date, settle_date, kind_raw, "
                "kind, amount, currency, balance_after, description, counterparty_name, "
                "counterparty_account, orig_amount, orig_currency, occurrence, seq, batch_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.number,
                    _row_key(row, occurrence),
                    row.tx_date.isoformat(),
                    row.settle_date.isoformat(),
                    row.kind_raw,
                    row.kind.value,
                    money.fmt(row.amount),
                    row.currency,
                    money.fmt(row.balance_after) if row.balance_after is not None else None,
                    row.description,
                    row.counterparty_name,
                    row.counterparty_account,
                    money.fmt(row.orig_amount) if row.orig_amount is not None else None,
                    row.orig_currency,
                    occurrence,
                    row.line,
                    batch_id,
                ),
            )
            stats.new += cur.rowcount
        _finish_batch(conn, batch_id, stats)
        rebuild_derived(conn)
    return stats


def rebuild_derived(conn: sqlite3.Connection) -> None:
    """Wszystko, co wynika z księgi: powiązania CSV (L0/L1), L2/L3, kategorie (M4a)."""
    relink_csv(conn)
    rebuild_links(conn)
    categorize.recategorize(conn)


# --- L0/L1: powiązanie wierszy CSV z księgą ----------------------------------------------------


def _csv_tx_date(r: sqlite3.Row) -> str:
    """Data transakcji: dla płatności kartą na rachunku z opisu, inaczej z kolumny."""
    return card_desc_date(r["description"]) or str(r["tx_date"])


def relink_csv(conn: sqlite3.Connection) -> None:
    """Przelicz powiązania wierszy CSV z księgą (L0 + L1) dla wszystkich kont."""
    auto_map_card_numbers(conn)
    conn.execute(
        "UPDATE csv_row SET status = 'unmapped', txn_id = NULL WHERE number NOT IN "
        "(SELECT value FROM account_alias WHERE source = 'csv_number') AND status != 'unmapped'"
    )
    accounts = conn.execute(
        "SELECT DISTINCT a.account_id, acc.kind FROM account_alias a "
        "JOIN account acc ON acc.id = a.account_id WHERE a.source = 'csv_number'"
    ).fetchall()
    for acc in accounts:
        _relink_account(conn, int(acc["account_id"]), is_card=acc["kind"] == "card")


def _relink_account(conn: sqlite3.Connection, account_id: int, *, is_card: bool) -> None:
    rows = conn.execute(
        "SELECT * FROM csv_row WHERE number IN (SELECT value FROM account_alias "
        "WHERE source = 'csv_number' AND account_id = ?) ORDER BY seq",
        (account_id,),
    ).fetchall()
    canonical, duplicates = _collapse_rows(rows)
    for r in duplicates:
        _set_csv(conn, r, "duplicate", None)

    boundary_row = conn.execute(
        "SELECT min(booking_date) AS d FROM txn WHERE account_id = ? AND source = 'eb' "
        "AND status = 'BOOK'",
        (account_id,),
    ).fetchone()
    boundary: str | None = boundary_row["d"] if boundary_row else None
    before = [r for r in canonical if boundary is None or r["settle_date"] < boundary]
    inside = [r for r in canonical if boundary is not None and r["settle_date"] >= boundary]

    for r in before:
        _ensure_csv_txn(conn, account_id, r)

    if not inside:
        return
    api = conn.execute(
        "SELECT * FROM txn WHERE account_id = ? AND source = 'eb' AND status = 'BOOK' "
        "AND booking_date >= ? ORDER BY booking_date, occurrence, id",
        (account_id, boundary),
    ).fetchall()
    matches = _match_inside(inside, api, is_card=is_card)
    for r in inside:
        target = matches.get(int(r["id"]))
        old = r["txn_id"]
        if old is not None and old != target:
            _drop_csv_txn(conn, int(old), target)
        if target is None:
            _set_csv(conn, r, "unmatched", None)
        else:
            _enrich(conn, target, r)
            _set_csv(conn, r, "enriched", target)


def _collapse_rows(rows: Sequence[sqlite3.Row]) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    """L0 na wierszach z bazy: dla każdego odcisku wiersze numeru z największą licznością."""
    by_sig: dict[str, dict[str, list[sqlite3.Row]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        sig = str(r["row_key"]).split(":")[0]
        by_sig[sig][r["number"]].append(r)
    canonical: list[sqlite3.Row] = []
    duplicates: list[sqlite3.Row] = []
    for per_number in by_sig.values():
        best = max(sorted(per_number), key=lambda n: len(per_number[n]))
        for number, group in per_number.items():
            (canonical if number == best else duplicates).extend(group)
    canonical.sort(key=lambda r: r["seq"])
    return canonical, duplicates


def _set_csv(conn: sqlite3.Connection, r: sqlite3.Row, status: str, txn_id: int | None) -> None:
    if r["status"] != status or r["txn_id"] != txn_id:
        conn.execute(
            "UPDATE csv_row SET status = ?, txn_id = ? WHERE id = ?", (status, txn_id, r["id"])
        )


def _csv_txn_values(r: sqlite3.Row) -> dict[str, Any]:
    amount = Decimal(r["amount"])
    settle = date.fromisoformat(r["settle_date"])
    return {
        "booking_date": r["settle_date"],
        "tx_date": _csv_tx_date(r),
        "amount": r["amount"],
        "currency": r["currency"],
        "orig_amount": r["orig_amount"],
        "orig_currency": r["orig_currency"],
        "description": r["description"],
        "counterparty_name": r["counterparty_name"],
        "counterparty_account": r["counterparty_account"],
        "balance_after": r["balance_after"],
        "fingerprint": fingerprint(settle, amount, r["description"]),
        "occurrence": r["occurrence"],
    }


def _ensure_csv_txn(conn: sqlite3.Connection, account_id: int, r: sqlite3.Row) -> None:
    values = _csv_txn_values(r)
    txn_id = r["txn_id"]
    current = None
    if txn_id is not None:
        current = conn.execute("SELECT * FROM txn WHERE id = ?", (txn_id,)).fetchone()
    if current is not None and current["source"] == "csv":
        if current["kind_source"] != "manual":
            values["kind"] = r["kind"]
            values["kind_source"] = "csv"
        _update_changed(conn, int(txn_id), current, values)
        _set_csv(conn, r, "inserted", int(txn_id))
        return
    now = now_iso()
    cur = conn.execute(
        "INSERT INTO txn (account_id, status, booking_date, tx_date, amount, currency, "
        "orig_amount, orig_currency, description, counterparty_name, counterparty_account, "
        "kind, kind_source, balance_after, fingerprint, occurrence, source, first_seen_at, "
        "updated_at) VALUES (?, 'BOOK', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'csv', ?, ?, ?, 'csv', ?, ?)",
        (
            account_id,
            values["booking_date"],
            values["tx_date"],
            values["amount"],
            values["currency"],
            values["orig_amount"],
            values["orig_currency"],
            values["description"],
            values["counterparty_name"],
            values["counterparty_account"],
            r["kind"],
            values["balance_after"],
            values["fingerprint"],
            values["occurrence"],
            now,
            now,
        ),
    )
    _set_csv(conn, r, "inserted", int(cur.lastrowid or 0))


def _drop_csv_txn(conn: sqlite3.Connection, txn_id: int, successor: int | None) -> None:
    """Transakcja z CSV weszła w okno API: usuń ją, ręczne ustawienia przenieś na następcę."""
    old = conn.execute("SELECT * FROM txn WHERE id = ? AND source = 'csv'", (txn_id,)).fetchone()
    if old is None:
        return
    if successor is not None:
        if old["kind_source"] == "manual":
            conn.execute(
                "UPDATE txn SET kind = ?, kind_source = 'manual' WHERE id = ?",
                (old["kind"], successor),
            )
        if old["budget_flag"]:
            conn.execute(
                "UPDATE txn SET budget_flag = ? WHERE id = ?", (old["budget_flag"], successor)
            )
        if old["category_source"] == "manual":
            conn.execute(
                "UPDATE txn SET category_id = ?, category_source = 'manual', rule_id = NULL "
                "WHERE id = ? AND category_source IS NOT 'manual'",
                (old["category_id"], successor),
            )
    conn.execute("DELETE FROM txn WHERE id = ?", (txn_id,))


def _enrich(conn: sqlite3.Connection, txn_id: int, r: sqlite3.Row) -> None:
    """CSV w oknie API: kwota i daty zostają z API, CSV dokłada to, czego API nie ma."""
    current = conn.execute("SELECT * FROM txn WHERE id = ?", (txn_id,)).fetchone()
    values: dict[str, Any] = {
        "balance_after": r["balance_after"],
        "orig_amount": r["orig_amount"],
        "orig_currency": r["orig_currency"],
        "tx_date": current["tx_date"] or _csv_tx_date(r),
        "counterparty_account": current["counterparty_account"] or r["counterparty_account"],
    }
    if current["kind_source"] != "manual":
        values["kind"] = r["kind"]
        values["kind_source"] = "csv"
    _update_changed(conn, txn_id, current, values)


def _match_inside(
    rows: Sequence[sqlite3.Row], api: Sequence[sqlite3.Row], *, is_card: bool
) -> dict[int, int]:
    """L1: wiersz CSV → transakcja API. Najpierw dokładnie (data rozliczenia = data
    księgowania, kwota), potem — tylko karta i tylko waluta obca — rozmyto."""
    free = {int(t["id"]): t for t in api}
    by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for t in api:
        by_key[(t["booking_date"], t["amount"])].append(int(t["id"]))
    out: dict[int, int] = {}
    for r in rows:
        for tid in by_key.get((r["settle_date"], r["amount"]), []):
            if tid in free:
                out[int(r["id"])] = tid
                del free[tid]
                break
    if not is_card:
        return out
    for r in rows:
        if int(r["id"]) in out or not r["orig_currency"]:
            continue
        settle = date.fromisoformat(r["settle_date"])
        amount = Decimal(r["amount"])
        best: tuple[Decimal, int, int] | None = None
        for tid, t in free.items():
            t_amount = Decimal(t["amount"])
            days = abs((date.fromisoformat(t["booking_date"]) - settle).days)
            if (
                days > FUZZY_DAYS
                or (t_amount < 0) != (amount < 0)
                or abs(t_amount - amount) > abs(amount) * FUZZY_SHARE
                or not same_merchant(r["description"], t["description"])
            ):
                continue
            key = (abs(t_amount - amount), days, tid)
            if best is None or key < best:
                best = key
        if best is not None:
            out[int(r["id"])] = best[2]
            del free[best[2]]
    return out


# --- L2/L3: przelewy własne i zwroty ------------------------------------------------------------


def _transfer_signal(t: sqlite3.Row, own_ibans: dict[str, int]) -> bool:
    if t["kind"] == Kind.CARD_REPAYMENT.value:
        return True
    # Kontrahent to INNE podlinkowane konto (własny numer bywa w polu przy wypłatach BLIK)
    other = own_ibans.get(t["counterparty_account"] or "")
    if other is not None and other != t["account_id"]:
        return True
    return fold(t["description"]).startswith("WCZESN.SPL")


def rebuild_links(conn: sqlite3.Connection) -> None:
    """Przelicz L2 (`transfer_group`) i L3 (`refund_of`) od zera — deterministycznie."""
    own = {
        r["iban"]: int(r["id"])
        for r in conn.execute("SELECT id, iban FROM account WHERE iban IS NOT NULL")
    }
    txns = conn.execute(
        "SELECT * FROM txn WHERE status = 'BOOK' ORDER BY booking_date, id"
    ).fetchall()
    groups: dict[int, str] = {}

    # L2: obciążenie konta A ↔ uznanie konta B, ta sama kwota, ≤ 3 dni, sygnał po którejś stronie
    credits: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for t in txns:
        if Decimal(t["amount"]) > 0:
            credits[t["amount"]].append(t)
    for t in txns:
        amount = Decimal(t["amount"])
        if amount >= 0 or int(t["id"]) in groups:
            continue
        signal = _transfer_signal(t, own)
        d = date.fromisoformat(t["booking_date"])
        best: tuple[int, int] | None = None
        for c in credits.get(money.fmt(-amount), []):
            cid = int(c["id"])
            if cid in groups or c["account_id"] == t["account_id"]:
                continue
            if not (signal or _transfer_signal(c, own)):
                continue
            days = abs((date.fromisoformat(c["booking_date"]) - d).days)
            if days <= TRANSFER_WINDOW.days and (best is None or (days, cid) < best):
                best = (days, cid)
        if best is not None:
            group = f"t{t['id']}"
            groups[int(t["id"])] = group
            groups[best[1]] = group
    # Strona bez pary (druga poza oknem danych) z mocnym sygnałem też jest przelewem
    for t in txns:
        if int(t["id"]) not in groups and _transfer_signal(t, own):
            groups[int(t["id"])] = f"t{t['id']}"

    # L3: zwrot → zakup u tego samego sprzedawcy, ≤ 90 dni wcześniej, kwota ≤ zakupu
    refunds: dict[int, int] = {}
    purchases = [
        t
        for t in txns
        if Decimal(t["amount"]) < 0
        and int(t["id"]) not in groups
        and t["kind"] in {k.value for k in PURCHASE_KINDS}
    ]
    for t in txns:
        if int(t["id"]) in groups or Decimal(t["amount"]) <= 0:
            continue
        if t["kind"] not in {k.value for k in REFUND_KINDS}:
            continue
        refunds_text = _merchant_text(t)
        d = date.fromisoformat(t["booking_date"])
        amount = Decimal(t["amount"])
        best_p: tuple[int, int, int] | None = None
        for p in purchases:
            pd = date.fromisoformat(p["booking_date"])
            if not (d - REFUND_WINDOW <= pd <= d) or -Decimal(p["amount"]) < amount:
                continue
            if not same_merchant(refunds_text, _merchant_text(p)):
                continue
            # najpierw to samo konto, potem najbliższa data
            key = (int(p["account_id"] != t["account_id"]), (d - pd).days, int(p["id"]))
            if best_p is None or key < best_p:
                best_p = key
        if best_p is not None:
            refunds[int(t["id"])] = best_p[2]

    for t in conn.execute("SELECT id, transfer_group, refund_of FROM txn").fetchall():
        tid = int(t["id"])
        new_group, refund = groups.get(tid), refunds.get(tid)
        if t["transfer_group"] != new_group or t["refund_of"] != refund:
            conn.execute(
                "UPDATE txn SET transfer_group = ?, refund_of = ? WHERE id = ?",
                (new_group, refund, tid),
            )


def _merchant_text(t: sqlite3.Row) -> str:
    """BLIK: sprzedawca w polu kontrahenta; karta: w opisie."""
    if t["kind"] in (Kind.BLIK.value, Kind.BLIK_REFUND.value) and t["counterparty_name"]:
        return str(t["counterparty_name"])
    return str(t["description"])


# --- uzgodnienie salda ----------------------------------------------------------------------------


@dataclass
class BalanceCheck:
    account_id: int
    days_checked: int = 0
    day_mismatches: list[tuple[str, Decimal]] = field(default_factory=list)
    snapshot_checks: list[tuple[str, Decimal, Decimal]] = field(default_factory=list)
    note: str = ""

    @property
    def ok(self) -> bool:
        return not self.day_mismatches and all(e == g for _, e, g in self.snapshot_checks)


def check_balances(conn: sqlite3.Connection) -> list[BalanceCheck]:
    """Uzgodnienie salda per konto.

    1. Rachunki z saldem w CSV: saldo otwarcia z najstarszego wiersza + transakcje księgi
       dzień po dniu = saldo końca dnia z CSV (sprawdza też transakcje z API w oknie CSV).
    2. Migawki ITBD z API: saldo otwarcia + transakcje znane w chwili migawki (z referencją
       z pobrania nie późniejszego niż migawka albo sprzed granicy API) = saldo banku.
       Bez salda otwarcia (karta) — porównanie różnic między migawkami.
    """
    out = []
    for acc in conn.execute("SELECT id FROM account ORDER BY id").fetchall():
        account_id = int(acc["id"])
        check = BalanceCheck(account_id)
        txns = conn.execute(
            "SELECT id, booking_date, amount, source FROM txn WHERE account_id = ? "
            "AND status = 'BOOK' ORDER BY booking_date, id",
            (account_id,),
        ).fetchall()
        opening = _csv_opening(conn, account_id)
        if opening is not None:
            open_date, open_balance, day_end = opening
            last_day = max(day_end)
            linked = {
                int(r["txn_id"])
                for r in conn.execute("SELECT txn_id FROM csv_row WHERE txn_id IS NOT NULL")
            }
            running = open_balance
            by_day: dict[str, Decimal] = defaultdict(Decimal)
            after_export = 0
            for t in txns:
                # Eksport robiony w trakcie dnia: z ostatniego dnia liczą się tylko transakcje,
                # które są w CSV — późniejsze z API sprawdza migawka salda
                if t["booking_date"] == last_day and int(t["id"]) not in linked:
                    after_export += 1
                    continue
                by_day[t["booking_date"]] += Decimal(t["amount"])
            for day in sorted(set(by_day) | set(day_end)):
                if day < open_date or day > last_day:
                    continue
                running += by_day.get(day, Decimal(0))
                if day in day_end:
                    check.days_checked += 1
                    if running != day_end[day]:
                        check.day_mismatches.append((day, running - day_end[day]))
            if after_export:
                check.note = (
                    f"ostatni dzień eksportu CSV ({last_day}) niepełny: "
                    f"{after_export} transakcji z API po eksporcie"
                )
        snapshots = conn.execute(
            "SELECT amount, fetched_at FROM balance_snapshot WHERE account_id = ? "
            "AND balance_type = 'ITBD' ORDER BY fetched_at",
            (account_id,),
        ).fetchall()
        known_sums = [
            (s["fetched_at"], Decimal(s["amount"]), _known_sum(conn, account_id, s["fetched_at"]))
            for s in snapshots
        ]
        if opening is not None:
            for at, bank, known in known_sums:
                check.snapshot_checks.append((at, bank, opening[1] + known))
        elif len(known_sums) >= 2:
            first_at, first_bank, first_known = known_sums[0]
            for at, bank, known in known_sums[1:]:
                check.snapshot_checks.append((at, bank - first_bank, known - first_known))
            check.note = f"różnice względem migawki {first_at}"
        else:
            check.note = "brak salda otwarcia i < 2 migawek — kontrola przy kolejnym pobraniu"
        out.append(check)
    return out


def _csv_opening(
    conn: sqlite3.Connection, account_id: int
) -> tuple[str, Decimal, dict[str, Decimal]] | None:
    rows = conn.execute(
        "SELECT settle_date, amount, balance_after, seq FROM csv_row "
        "WHERE txn_id IN (SELECT id FROM txn WHERE account_id = ?) "
        "AND balance_after IS NOT NULL ORDER BY settle_date, seq DESC",
        (account_id,),
    ).fetchall()
    if not rows:
        return None
    oldest = rows[0]
    open_balance = Decimal(oldest["balance_after"]) - Decimal(oldest["amount"])
    day_end: dict[str, Decimal] = {}
    for r in rows:  # w obrębie dnia rosnąco od najstarszego — ostatni nadpisuje
        day_end[r["settle_date"]] = Decimal(r["balance_after"])
    return oldest["settle_date"], open_balance, day_end


def _known_sum(conn: sqlite3.Connection, account_id: int, at: str) -> Decimal:
    limit = (datetime.fromisoformat(at) + timedelta(minutes=10)).isoformat()
    rows = conn.execute(
        "SELECT t.amount FROM txn t WHERE t.account_id = ? AND t.status = 'BOOK' AND ("
        " t.source = 'csv' OR EXISTS (SELECT 1 FROM txn_ref r JOIN import_batch b "
        " ON b.id = r.batch_id WHERE r.txn_id = t.id AND b.fetched_at <= ?))",
        (account_id, limit),
    ).fetchall()
    return money.total(r["amount"] for r in rows)
