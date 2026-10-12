"""Paragony Lidl Plus (M29 E4): odczyt pliku z add-onu Lidl i dopasowanie do płatności.

Add-on Lidl zapisuje `/share/lidl/receipts.json`: paragony z kwotą zapłaconą podzieloną na kategorie
produktów (`food`, `drugstore`, `kids`, `nonfood`; suma części = zapłacono). Paragon łączy się
z wydatkiem z opisem „LIDL” o tej samej kwocie co do grosza i dacie ±3 dni, gdy po obu stronach jest
dokładnie jeden kandydat; niejednoznaczne czekają na wybór w karcie transakcji (E5). Kategorie Lidla
mapujemy na podkategorie (kv, edytowalne).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from budget import money, split
from budget.categorize import engine, taxonomy
from budget.categorize.taxonomy import TaxonomyError
from budget.storage.db import kv_get, kv_set

log = logging.getLogger(__name__)

WINDOW = timedelta(days=3)
# panel add-onu Lidl w HA; `/paragony/<id>` otwiera paragon (Lidl ≥ 0.19.1)
LIDL_PANEL = "/app/f0987e0f_lidl"
MAP_KEY = "lidl_category_map"
# kategoria produktu Lidla → (etykieta, domyślna podkategoria Budżetu)
CATEGORIES = {
    "food": ("Spożywcze", "spozywcze"),
    "drugstore": ("Drogeria", "drogeria"),
    "kids": ("Dla dzieci", "dzieci-zakupy"),
    "nonfood": ("Inne", "zakupy-inne"),
}
# wydatek w Lidlu: tekst jak w wyszukiwaniu Transakcji (`fold` bez ogonków, z kontrahentem)
_EXPENSE = (
    "status = 'BOOK' AND transfer_group IS NULL AND amount LIKE '-%' AND fold(description || ' ' "
    "|| coalesce(counterparty_name, '') || ' ' || coalesce(merchant, '')) LIKE '%lidl%'"
)


@dataclass(frozen=True)
class Receipt:
    id: str
    day: date
    paid: Decimal
    parts: dict[str, Decimal]
    cash: bool = False  # zapłacony gotówką: bez płatności w banku


@dataclass(frozen=True)
class MatchResult:
    linked: int
    ambiguous: int
    unmatched: int
    # zł przesunięte z podkategorii spożywczej do innych (raport M29 E6)
    moved: Decimal = Decimal(0)


def load(path: Path) -> list[Receipt]:
    """Paragony z pliku; brak pliku albo zły format = pusta lista (Lidla może nie być)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        log.warning("Paragony Lidl: nieczytelny %s (%s)", path, exc)
        return []
    out = []
    for r in (data.get("receipts") if isinstance(data, dict) else None) or []:
        try:
            paid = money.parse(str(r["paid"]))
            parts = {str(k): money.parse(str(v)) or Decimal(0) for k, v in r["parts"].items()}
            if paid is None:
                continue
            cash = "got" in str(r.get("payment") or "").lower()  # „Gotówka”
            out.append(Receipt(str(r["id"]), date.fromisoformat(r["day"]), paid, parts, cash))
        except (KeyError, TypeError, AttributeError, ValueError):  # AmountError to ValueError
            continue
    return out


def links(conn: sqlite3.Connection, txn_ids: list[int] | None = None) -> dict[int, str]:
    """Transakcja → paragon (wszystkie albo tylko `txn_ids`)."""
    sql, args = "SELECT txn_id, ticket_id FROM txn_lidl", list(txn_ids or [])
    if txn_ids is not None:
        sql += f" WHERE txn_id IN ({','.join('?' * len(args))})"
    return {int(t): str(r) for t, r in conn.execute(sql, args)}


def _free(conn: sqlite3.Connection, receipts: list[Receipt]) -> list[Receipt]:
    used = set(links(conn).values())
    return [r for r in receipts if r.id not in used and r.paid > 0 and not r.cash]


def _rejected(conn: sqlite3.Connection) -> set[tuple[int, str]]:
    return {
        (int(t), str(r)) for t, r in conn.execute("SELECT txn_id, ticket_id FROM txn_lidl_reject")
    }


def _near(receipt: Receipt, day: str) -> bool:
    return abs(date.fromisoformat(day) - receipt.day) <= WINDOW


def match(conn: sqlite3.Connection, receipts: list[Receipt]) -> MatchResult:
    """Łączy pary jednoznaczne po obu stronach; paragon i transakcja najwyżej raz."""
    pending = _free(conn, receipts)
    found: dict[str, list[int]] = {r.id: [] for r in pending}
    if pending:
        lo = min(r.day for r in pending) - WINDOW
        hi = max(r.day for r in pending) + WINDOW
        by_amount: dict[Decimal, list[tuple[int, str]]] = {}
        for t, amount, day in conn.execute(
            f"SELECT id, amount, coalesce(tx_date, booking_date) FROM txn WHERE {_EXPENSE} "
            "AND coalesce(tx_date, booking_date) BETWEEN ? AND ? "
            "AND id NOT IN (SELECT txn_id FROM txn_lidl) ORDER BY 3, id",
            (lo.isoformat(), hi.isoformat()),
        ):
            by_amount.setdefault(-Decimal(amount), []).append((int(t), day))
        rejected = _rejected(conn)
        for r in pending:
            found[r.id] = [
                t
                for t, day in by_amount.get(r.paid, [])
                if _near(r, day) and (t, r.id) not in rejected
            ]
    claims = Counter(t for tids in found.values() for t in tids)
    pairs = []
    for r in pending:
        tids = found[r.id]
        if len(tids) == 1 and claims[tids[0]] == 1:
            pairs.append((tids[0], r))
    cmap = category_map(conn) if pairs else {}
    moved = sum((_link(conn, tid, r, "auto", cmap) for tid, r in pairs), Decimal(0))
    unmatched = sum(1 for tids in found.values() if not tids)
    return MatchResult(len(pairs), len(found) - len(pairs) - unmatched, unmatched, moved)


def receipts_for_txn(conn: sqlite3.Connection, path: Path, txn_id: int) -> list[Receipt]:
    """Wolne paragony pasujące do tej (niepołączonej) transakcji — wybór przy niejednoznacznych.
    Plik czytamy tylko dla wydatku w Lidlu."""
    row = conn.execute(
        f"SELECT amount, coalesce(tx_date, booking_date) FROM txn WHERE id = ? AND {_EXPENSE} "
        "AND id NOT IN (SELECT txn_id FROM txn_lidl)",
        (txn_id,),
    ).fetchone()
    if row is None:
        return []
    rejected = {r for t, r in _rejected(conn) if t == txn_id}
    return [
        r
        for r in _free(conn, load(path))
        if r.paid == -Decimal(row[0]) and _near(r, row[1]) and r.id not in rejected
    ]


def unlink(conn: sqlite3.Connection, txn_id: int) -> None:
    """„To nie ten paragon”: odłącza i zapamiętuje parę; podział z paragonu wraca do kategorii
    automatycznej (ręcznych zmian użytkownika nie ruszamy). Po nim `engine.recategorize`."""
    ticket = links(conn, [txn_id]).get(txn_id)
    if ticket is None:
        return
    conn.execute("DELETE FROM txn_lidl WHERE txn_id = ?", (txn_id,))
    conn.execute("INSERT OR IGNORE INTO txn_lidl_reject VALUES (?, ?)", (txn_id, ticket))
    if conn.execute(
        "SELECT 1 FROM txn_split WHERE txn_id = ? AND source = 'lidl'", (txn_id,)
    ).fetchone():
        split.clear(conn, txn_id)


def choose(conn: sqlite3.Connection, txn_id: int, receipt: Receipt) -> None:
    """Ręczny wybór paragonu dla transakcji."""
    _link(conn, txn_id, receipt, "chosen", category_map(conn))


def _link(
    conn: sqlite3.Connection, txn_id: int, receipt: Receipt, status: str, cmap: dict[str, int]
) -> Decimal:
    conn.execute(
        "INSERT INTO txn_lidl (txn_id, ticket_id, status) VALUES (?, ?, ?)",
        (txn_id, receipt.id, status),
    )
    return _apply(conn, txn_id, receipt, cmap)


def _apply(
    conn: sqlite3.Connection, txn_id: int, receipt: Receipt, cmap: dict[str, int]
) -> Decimal:
    """Kategorie z paragonu, raz — przy połączeniu: wiele podkategorii = podział (`source='lidl'`),
    jedna = zwykła kategoria. Ręcznej kategorii ani podziału użytkownika nie ruszamy, a późniejsza
    zmiana użytkownika wygrywa (nic nie stosujemy ponownie). Zwraca zł poza spożywczymi."""
    row = conn.execute(
        "SELECT category_id, category_source FROM txn WHERE id = ?", (txn_id,)
    ).fetchone()
    if row is None or row["category_source"] == "manual":
        return Decimal(0)
    sums: dict[int, Decimal] = {}
    for part, amount in receipt.parts.items():
        cat = cmap.get(part, cmap["food"])
        sums[cat] = sums.get(cat, Decimal(0)) - amount
    parts = sorted(((c, a) for c, a in sums.items() if a), key=lambda p: -abs(p[1]))
    try:
        if len(parts) > 1:
            split.save(conn, txn_id, parts, source="lidl")
        elif parts and parts[0][0] != row["category_id"]:
            engine.set_manual(conn, txn_id, parts[0][0])
        else:
            return Decimal(0)  # bez zmiany
    except TaxonomyError as exc:  # np. zwrot kaucji większy niż część: zostaje kategoria transakcji
        log.info("Paragon Lidl %s: bez podziału (%s)", receipt.id, exc)
        return Decimal(0)
    return sum((-a for c, a in parts if c != cmap["food"]), Decimal(0))


def category_map(conn: sqlite3.Connection) -> dict[str, int]:
    """Kategoria Lidla → podkategoria Budżetu (kv; domyślnie Spożywcze, Drogeria, Zakupy dla dzieci,
    Inne zakupy)."""
    saved = kv_get(conn, MAP_KEY) or {}
    slugs = taxonomy.by_slug(conn)
    return {k: int(saved.get(k) or slugs[slug].id) for k, (_, slug) in CATEGORIES.items()}


def set_category_map(conn: sqlite3.Connection, mapping: dict[str, int]) -> None:
    leaves = taxonomy.leaves(conn)
    if set(mapping) != set(CATEGORIES) or any(c not in leaves for c in mapping.values()):
        raise TaxonomyError("Każda kategoria Lidla potrzebuje podkategorii.")
    kv_set(conn, MAP_KEY, mapping)
