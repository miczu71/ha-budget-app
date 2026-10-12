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
LIDL_PANEL = (
    "/app/f0987e0f_lidl"  # panel add-onu Lidl w HA; otwiera paragon z `url_path` (Lidl ≥ 0.19.1)
)
MAP_KEY = "lidl_category_map"
DEFAULT_MAP = {
    "food": "spozywcze",
    "drugstore": "drogeria",
    "kids": "dzieci-zakupy",
    "nonfood": "zakupy-inne",
}
LABELS = {"food": "Spożywcze", "drugstore": "Drogeria", "kids": "Dla dzieci", "nonfood": "Inne"}
_EXPENSES = (
    "SELECT id, amount, coalesce(tx_date, booking_date) AS day FROM txn WHERE status = 'BOOK' "
    "AND transfer_group IS NULL AND amount LIKE '-%' "
    "AND upper(coalesce(merchant, '') || ' ' || description) LIKE '%LIDL%' "
    "AND coalesce(tx_date, booking_date) BETWEEN ? AND ?"
)


@dataclass(frozen=True)
class Receipt:
    id: str
    day: date
    paid: Decimal
    parts: dict[str, Decimal]
    url_path: str


@dataclass(frozen=True)
class MatchResult:
    linked: int
    ambiguous: int
    unmatched: int
    moved: Decimal = Decimal(
        0
    )  # zł przesunięte z podkategorii spożywczej do innych (raport M29 E6)


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
            out.append(
                Receipt(
                    str(r["id"]),
                    date.fromisoformat(r["day"]),
                    paid,
                    parts,
                    str(r.get("url_path", "")),
                )
            )
        except (KeyError, TypeError, AttributeError, ValueError):  # AmountError to ValueError
            continue
    return out


def links(conn: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    """Transakcja → (paragon, status)."""
    return {
        int(r[0]): (str(r[1]), str(r[2]))
        for r in conn.execute("SELECT txn_id, ticket_id, status FROM txn_lidl")
    }


def _expenses(
    conn: sqlite3.Connection, receipts: list[Receipt]
) -> dict[Decimal, list[tuple[int, date]]]:
    if not receipts:
        return {}
    lo, hi = min(r.day for r in receipts) - WINDOW, max(r.day for r in receipts) + WINDOW
    linked = set(links(conn))
    out: dict[Decimal, list[tuple[int, date]]] = {}
    for tid, amount, day in conn.execute(
        _EXPENSES + " ORDER BY day, id", (lo.isoformat(), hi.isoformat())
    ):
        if tid not in linked:
            out.setdefault(-Decimal(amount), []).append((int(tid), date.fromisoformat(day)))
    return out


def _candidates(by_amount: dict[Decimal, list[tuple[int, date]]], receipt: Receipt) -> list[int]:
    return [tid for tid, day in by_amount.get(receipt.paid, []) if abs(day - receipt.day) <= WINDOW]


def candidates(conn: sqlite3.Connection, receipt: Receipt) -> list[int]:
    """Niepołączone wydatki pasujące do paragonu (kwota, data ±3 dni)."""
    return _candidates(_expenses(conn, [receipt]), receipt)


def match(conn: sqlite3.Connection, receipts: list[Receipt]) -> MatchResult:
    """Łączy pary jednoznaczne po obu stronach; paragon i transakcja najwyżej raz."""
    used = {ticket for ticket, _ in links(conn).values()}
    pending = [r for r in receipts if r.id not in used and r.paid > 0]
    by_amount = _expenses(conn, pending)
    found = {r.id: _candidates(by_amount, r) for r in pending}
    claims: dict[int, int] = {}
    for tids in found.values():
        for tid in tids:
            claims[tid] = claims.get(tid, 0) + 1
    pairs = [(t[0], r) for r in pending if len(t := found[r.id]) == 1 and claims[t[0]] == 1]
    cmap = category_map(conn) if pairs else {}
    moved = sum((_link(conn, tid, r, "auto", cmap) for tid, r in pairs), Decimal(0))
    unmatched = sum(1 for tids in found.values() if not tids)
    return MatchResult(len(pairs), len(found) - len(pairs) - unmatched, unmatched, moved)


def receipts_for_txn(
    conn: sqlite3.Connection, receipts: list[Receipt], txn_id: int
) -> list[Receipt]:
    """Wolne paragony pasujące do tej transakcji (do wyboru przy niejednoznacznych, E5)."""
    used = {ticket for ticket, _ in links(conn).values()}
    free = [r for r in receipts if r.id not in used and r.paid > 0]
    by_amount = _expenses(conn, free)
    return [r for r in free if txn_id in _candidates(by_amount, r)]


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
    except TaxonomyError as exc:  # np. zwrot kaucji większy niż część: zostaje kategoria transakcji
        log.info("Paragon Lidl %s: bez podziału (%s)", receipt.id, exc)
        return Decimal(0)
    return sum((-a for c, a in parts if c != cmap["food"]), Decimal(0))


def category_map(conn: sqlite3.Connection) -> dict[str, int]:
    """Kategoria Lidla → podkategoria Budżetu (kv; domyślnie Spożywcze, Drogeria, Zakupy dla dzieci,
    Inne zakupy)."""
    saved = kv_get(conn, MAP_KEY) or {}
    slugs = taxonomy.by_slug(conn)
    return {k: int(saved.get(k) or slugs[slug].id) for k, slug in DEFAULT_MAP.items()}


def set_category_map(conn: sqlite3.Connection, mapping: dict[str, int]) -> None:
    leaves = taxonomy.leaves(conn)
    if set(mapping) != set(DEFAULT_MAP) or any(c not in leaves for c in mapping.values()):
        raise TaxonomyError("Każda kategoria Lidla potrzebuje podkategorii.")
    kv_set(conn, MAP_KEY, mapping)
