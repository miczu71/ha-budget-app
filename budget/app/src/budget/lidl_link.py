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
from functools import lru_cache
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
# sieć paragonu (pole `chain`) → wzorce w tekście wydatku (`fold`, jak `LIKE` w Transakcjach)
CHAIN_PATTERNS = {"lidl": ("lidl",), "biedronka": ("biedronka", "jeronimo")}


def _expense(chain: str) -> str:
    """Wydatek w sieci: tekst jak w wyszukiwaniu Transakcji (`fold` bez ogonków, z kontrahentem)."""
    text = (
        "fold(description || ' ' || coalesce(counterparty_name, '') || ' ' "
        "|| coalesce(merchant, ''))"
    )
    any_pattern = " OR ".join(f"{text} LIKE '%{p}%'" for p in CHAIN_PATTERNS[chain])
    return f"status = 'BOOK' AND transfer_group IS NULL AND amount LIKE '-%' AND ({any_pattern})"


@dataclass(frozen=True)
class Receipt:
    id: str
    day: date
    paid: Decimal
    parts: dict[str, Decimal]
    cash: bool = False  # zapłacony gotówką: bez płatności w banku
    country: str = "PL"  # zagraniczny: `paid` w PLN po NBP, kwota z banku może się różnić
    currency: str = "PLN"  # waluta oryginału (chip wyboru w _txn_category.html)
    paid_orig: Decimal | None = None
    chain: str = "lidl"  # sieć (`lidl`/`biedronka`); paragon łączy się tylko z wydatkiem tej sieci


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
    unknown_chain = 0
    for r in (data.get("receipts") if isinstance(data, dict) else None) or []:
        try:
            paid = money.parse(str(r["paid"]))
            parts = {str(k): money.parse(str(v)) or Decimal(0) for k, v in r["parts"].items()}
            if paid is None:
                continue
            cash = "got" in str(r.get("payment") or "").lower()  # „Gotówka”
            country = r.get("country")
            currency = r.get("currency")
            try:
                paid_orig = (
                    money.parse(str(r["paid_orig"])) if r.get("paid_orig") is not None else None
                )
            except ValueError:
                paid_orig = None
            chain = r.get("chain")
            if chain in (None, ""):
                chain = "lidl"  # eksport sprzed E28 (tylko Lidl)
            elif chain not in CHAIN_PATTERNS:
                unknown_chain += 1  # nieznana sieć: nie zgadujemy Lidla, paragon pomijamy
                continue
            out.append(
                Receipt(
                    str(r["id"]),
                    date.fromisoformat(r["day"]),
                    paid,
                    parts,
                    cash,
                    country.upper() if isinstance(country, str) and country else "PL",
                    currency if isinstance(currency, str) and currency else "PLN",
                    paid_orig,
                    chain,
                )
            )
        except (KeyError, TypeError, AttributeError, ValueError):  # AmountError to ValueError
            continue
    if unknown_chain:
        log.warning("Paragony: pominięto %d z nieznaną siecią (pole chain)", unknown_chain)
    return out


def links(conn: sqlite3.Connection, txn_ids: list[int] | None = None) -> dict[int, str]:
    """Transakcja → paragon (wszystkie albo tylko `txn_ids`)."""
    sql, args = "SELECT txn_id, ticket_id FROM txn_lidl", list(txn_ids or [])
    if txn_ids is not None:
        sql += f" WHERE txn_id IN ({','.join('?' * len(args))})"
    return {int(t): str(r) for t, r in conn.execute(sql, args)}


def _meta(path: Path) -> dict[str, tuple[str, str]]:
    """Paragon → (kraj, sieć) dla pliku; jeden cache po mtime (nowy eksport go unieważnia)."""
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return {}
    return _meta_cached(str(path), stamp)


@lru_cache(maxsize=2)
def _meta_cached(path: str, _mtime_ns: int) -> dict[str, tuple[str, str]]:
    return {r.id: (r.country, r.chain) for r in load(Path(path))}


def foreign_ids(path: Path, ids: set[str]) -> set[str]:
    """Spośród `ids` te paragony, które są spoza Polski (link do zakładki Kraje w Lidlu)."""
    meta = _meta(path) if ids else {}
    return {i for i in ids if meta.get(i, ("PL", ""))[0] != "PL"}


def chains(path: Path, ids: set[str]) -> dict[str, str]:
    """Spośród `ids` paragon → sieć (`lidl`/`biedronka`); paragony spoza pliku pomijamy."""
    meta = _meta(path) if ids else {}
    return {i: meta[i][1] for i in ids if i in meta}


def _free(conn: sqlite3.Connection, receipts: list[Receipt]) -> list[Receipt]:
    used = set(links(conn).values())
    return [r for r in receipts if r.id not in used and r.paid > 0 and not r.cash]


def _rejected(conn: sqlite3.Connection) -> set[tuple[int, str]]:
    return {
        (int(t), str(r)) for t, r in conn.execute("SELECT txn_id, ticket_id FROM txn_lidl_reject")
    }


def _near(receipt: Receipt, day: str) -> bool:
    return abs(date.fromisoformat(day) - receipt.day) <= WINDOW


FOREIGN_TOLERANCE = Decimal("0.05")


def _amount_ok(receipt: Receipt, bank_amount: Decimal) -> bool:
    """Kwota z banku (dodatnia): polski co do grosza, zagraniczny w tolerancji 5% (kurs banku)."""
    if receipt.country == "PL":
        return receipt.paid == bank_amount
    return abs(bank_amount - receipt.paid) <= FOREIGN_TOLERANCE * receipt.paid


def match(conn: sqlite3.Connection, receipts: list[Receipt]) -> MatchResult:
    """Łączy pary jednoznaczne po obu stronach; paragon i transakcja najwyżej raz."""
    pending = _free(conn, receipts)
    found: dict[str, list[int]] = {r.id: [] for r in pending}
    if pending:
        lo = min(r.day for r in pending) - WINDOW
        hi = max(r.day for r in pending) + WINDOW
        rejected = _rejected(conn)
        for chain in {r.chain for r in pending}:  # paragon sieci X tylko do wydatku sieci X
            candidates: list[tuple[int, Decimal, str]] = []
            by_amount: dict[Decimal, list[tuple[int, str]]] = {}
            for t, amount, day in conn.execute(
                f"SELECT id, amount, coalesce(tx_date, booking_date) "
                f"FROM txn WHERE {_expense(chain)} "
                "AND coalesce(tx_date, booking_date) BETWEEN ? AND ? "
                "AND id NOT IN (SELECT txn_id FROM txn_lidl) ORDER BY 3, id",
                (lo.isoformat(), hi.isoformat()),
            ):
                candidates.append((int(t), -Decimal(amount), day))
                by_amount.setdefault(-Decimal(amount), []).append((int(t), day))
            for r in (p for p in pending if p.chain == chain):
                if r.country == "PL":  # co do grosza: indeks po kwocie zamiast skanu
                    same = by_amount.get(r.paid, [])
                else:
                    same = [(t, day) for t, amount, day in candidates if _amount_ok(r, amount)]
                found[r.id] = [t for t, day in same if _near(r, day) and (t, r.id) not in rejected]
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


def _txn_chain(conn: sqlite3.Connection, txn_id: int) -> tuple[str, sqlite3.Row] | None:
    """Sieć niepołączonej transakcji (pierwsza pasująca) i jej (kwota, dzień); `None` = nie sieć."""
    for chain in CHAIN_PATTERNS:
        row = conn.execute(
            f"SELECT amount, coalesce(tx_date, booking_date) "
            f"FROM txn WHERE id = ? AND {_expense(chain)} "
            "AND id NOT IN (SELECT txn_id FROM txn_lidl)",
            (txn_id,),
        ).fetchone()
        if row is not None:
            return chain, row
    return None


def receipts_for_txn(conn: sqlite3.Connection, path: Path, txn_id: int) -> list[Receipt]:
    """Wolne paragony pasujące do tej (niepołączonej) transakcji — wybór przy niejednoznacznych.
    Plik czytamy tylko dla wydatku w sieci (Lidl albo Biedronka); paragony innej sieci odpadają."""
    found = _txn_chain(conn, txn_id)
    if found is None:
        return []
    chain, row = found
    rejected = {r for t, r in _rejected(conn) if t == txn_id}
    return [
        r
        for r in _free(conn, load(path))
        if r.chain == chain
        and _amount_ok(r, -Decimal(row[0]))
        and _near(r, row[1])
        and r.id not in rejected
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
        "SELECT category_id, category_source, amount FROM txn WHERE id = ?", (txn_id,)
    ).fetchone()
    if row is None or row["category_source"] == "manual":
        return Decimal(0)
    receipt_parts = receipt.parts
    if receipt.country != "PL":
        receipt_parts = _scaled(receipt.parts, -Decimal(row["amount"]))
    sums: dict[int, Decimal] = {}
    for part, amount in receipt_parts.items():
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


def _scaled(parts: dict[str, Decimal], target: Decimal) -> dict[str, Decimal]:
    """Części proporcjonalnie do kwoty z banku; różnica groszy trafia do największej części."""
    total = sum(parts.values(), Decimal(0))
    if not total or not parts:
        return parts
    out = {k: (v * target / total).quantize(money.CENT) for k, v in parts.items()}
    biggest = max(parts, key=lambda k: abs(parts[k]))
    out[biggest] += target - sum(out.values(), Decimal(0))
    return out


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
