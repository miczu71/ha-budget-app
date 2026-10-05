"""Raport księgi — same liczby (bez opisów, kontrahentów i pełnych numerów).

`build()` zwraca dane dla panelu, `format_text()` — wiersze dla CLI.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from budget import ledger
from budget.ledger import BalanceCheck
from budget.logging_utils import mask_iban


@dataclass(frozen=True)
class SourceRange:
    source: str
    count: int
    first: str | None
    last: str | None


@dataclass(frozen=True)
class AccountSummary:
    id: int
    kind: str
    currency: str
    iban_masked: str | None
    display_name: str | None
    include_in_budget: bool
    sources: list[SourceRange]


@dataclass(frozen=True)
class CsvRowCount:
    account_id: int | None  # None = numer bez przypisanego konta
    status: str
    count: int


@dataclass
class LedgerReport:
    accounts: list[AccountSummary] = field(default_factory=list)
    csv_rows: list[CsvRowCount] = field(default_factory=list)
    transfer_pairs: int = 0
    transfer_unpaired: int = 0
    repayments_paired: int = 0
    repayments_total: int = 0
    refunds_linked: int = 0
    refunds_total: int = 0
    kind_sources: dict[str, int] = field(default_factory=dict)
    balance_checks: list[BalanceCheck] = field(default_factory=list)


def accounts(conn: sqlite3.Connection) -> list[AccountSummary]:
    """Konta z zakresami transakcji per źródło — tanie, bez reszty raportu (ekran Konta)."""
    out = []
    for acc in conn.execute("SELECT * FROM account ORDER BY id").fetchall():
        rows = conn.execute(
            "SELECT source, count(*) AS n, min(booking_date) AS d0, max(booking_date) AS d1 "
            "FROM txn WHERE account_id = ? AND status = 'BOOK' GROUP BY source ORDER BY source",
            (acc["id"],),
        ).fetchall()
        out.append(
            AccountSummary(
                id=int(acc["id"]),
                kind=acc["kind"],
                currency=acc["currency"],
                iban_masked=mask_iban(acc["iban"]),
                display_name=acc["display_name"],
                include_in_budget=bool(acc["include_in_budget"]),
                sources=[SourceRange(r["source"], int(r["n"]), r["d0"], r["d1"]) for r in rows],
            )
        )
    return out


def build(conn: sqlite3.Connection) -> LedgerReport:
    rep = LedgerReport(accounts=accounts(conn))
    rep.csv_rows = [
        CsvRowCount(r["acc"], r["status"], int(r["n"]))
        for r in conn.execute(
            "SELECT a.account_id AS acc, c.status, count(*) AS n FROM csv_row c "
            "LEFT JOIN account_alias a ON a.source = 'csv_number' AND a.value = c.number "
            "GROUP BY 1, 2 ORDER BY acc IS NULL, acc, 2"
        )
    ]
    sizes = Counter(
        int(r["n"])
        for r in conn.execute(
            "SELECT count(*) AS n FROM txn WHERE transfer_group IS NOT NULL GROUP BY transfer_group"
        )
    )
    rep.transfer_pairs, rep.transfer_unpaired = sizes.get(2, 0), sizes.get(1, 0)
    repay = conn.execute(
        "SELECT count(*) AS n, sum(transfer_group IN (SELECT transfer_group FROM txn "
        "GROUP BY transfer_group HAVING count(*) = 2)) AS paired FROM txn t "
        "WHERE kind = 'card_repayment' AND amount LIKE '-%'"
    ).fetchone()
    rep.repayments_paired, rep.repayments_total = int(repay["paired"] or 0), int(repay["n"])
    refunds = conn.execute(
        "SELECT count(*) AS n, count(refund_of) AS linked FROM txn "
        "WHERE kind IN ('card_refund', 'blik_refund') AND transfer_group IS NULL"
    ).fetchone()
    rep.refunds_linked, rep.refunds_total = int(refunds["linked"]), int(refunds["n"])
    rep.kind_sources = {
        r["kind_source"]: int(r["n"])
        for r in conn.execute("SELECT kind_source, count(*) AS n FROM txn GROUP BY 1 ORDER BY 1")
    }
    rep.balance_checks = ledger.check_balances(conn)
    return rep


def format_text(rep: LedgerReport) -> list[str]:
    out = ["", "== Księga =="]
    for acc in rep.accounts:
        parts = ", ".join(f"{s.source} {s.count} ({s.first} … {s.last})" for s in acc.sources)
        out.append(
            f"#{acc.id} {acc.kind:7} {acc.currency} {acc.iban_masked}: {parts or 'brak transakcji'}"
        )
    out += ["", "== Wiersze CSV =="]
    out += [
        f"konto #{r.account_id if r.account_id is not None else '-'}: {r.status} {r.count}"
        for r in rep.csv_rows
    ]
    out += ["", "== Przelewy własne (L2) i zwroty (L3) =="]
    out.append(f"pary: {rep.transfer_pairs}, strona bez pary: {rep.transfer_unpaired}")
    out.append(
        f"spłaty karty (strona rachunku): {rep.repayments_paired}/{rep.repayments_total} "
        "sparowanych"
    )
    out.append(f"zwroty powiązane z zakupem: {rep.refunds_linked}/{rep.refunds_total}")
    out.append("źródło typu: " + ", ".join(f"{k} {n}" for k, n in rep.kind_sources.items()))
    out += ["", "== Uzgodnienie salda =="]
    out += [balance_line(check) for check in rep.balance_checks]
    return out


def balance_line(check: BalanceCheck) -> str:
    line = f"#{check.account_id}: {check.status}"
    if check.days_checked:
        line += f"; dni z saldem CSV {check.days_checked}, rozbieżnych {len(check.day_mismatches)}"
        if check.day_mismatches:
            day, diff = check.day_mismatches[0]
            line += f" (pierwszy {day}: {diff:+})"
    for at, bank, calc in check.snapshot_checks:
        line += f"; migawka {at[:16]}: bank {bank} / księga {calc}"
    if check.note:
        line += f"; {check.note}"
    if check.base_at:
        line += " (baza ustawiona w panelu)"
    if check.status == "W DRODZE":
        line += (
            f"; różnica od {check.diff_since[:16] if check.diff_since else '?'} — autoryzacja "
            "albo uznanie jeszcze niewidoczne w transakcjach API"
        )
    return line
