"""Silnik kategorii: deterministyczne przeliczenie od zera (wzorzec `ledger.rebuild_links`).

Kategoria transakcji = pierwsze pasujące źródło:
1. `manual` — ręczna zmiana w panelu (nigdy nie nadpisywana),
2. `refund` — zwrot (`refund_of`, L3) dziedziczy końcową kategorię zakupu,
3. `rule` — reguły użytkownika wg priorytetu,
4. `dictionary` — wbudowany słownik sieci,
5. `kind` — domyślna kategoria typu (gotówka, opłata, rata kredytu),
6. `learned` — pamięć sprzedawcy (M7 E2): ręczne decyzje u tego samego (sprzedawca, kierunek), gdy
   wszystkie są zgodne (`learn.memory`, k = 1); poprawka na inną kategorię wyłącza pamięć,
w przeciwnym razie brak kategorii. Przelewy wewnętrzne (`transfer_group`) kategorii nie mają.

Przeliczenie idzie po każdym imporcie i synchronizacji oraz po zmianie reguł; podgląd reguły
liczy to samo w pamięci i porównuje z zapisanym stanem.
"""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from functools import lru_cache

from budget import review
from budget.categorize import learn, merchants, taxonomy
from budget.categorize.merchants import Dictionary
from budget.categorize.rules import Facts, Rule, _norm, all_rules
from budget.kinds import Kind
from budget.storage.db import kv_get, kv_set

KIND_DEFAULTS = {
    Kind.CASH.value: "wyplaty-gotowki",
    Kind.FEE.value: "oplaty-bankowe",
    Kind.LOAN.value: "kredyt",
}
PREVIEW_SAMPLES = 10
PREVIEW_ID = -1  # id reguły w podglądzie, zanim trafi do bazy
LEARNED_STATS_KEY = "learned_stats"  # {"confirmed": n, "corrected": n} — `set_manual`


@dataclass(frozen=True)
class Assignment:
    category_id: int | None
    source: str | None
    rule_id: int | None
    merchant: str


@dataclass
class _Txn:
    id: int
    date: str
    amount: Decimal
    facts: Facts
    entry: merchants.Entry | None
    transfer: bool
    refund_of: int | None
    current: Assignment
    is_manual: bool


@lru_cache(maxsize=50_000)
def _derive(
    dictionary: Dictionary, kind: str, description: str | None, counterparty: str | None
) -> tuple[str, merchants.Entry | None]:
    """Nazwa sprzedawcy i wpis słownika — zależą tylko od tekstu (pamięć między podglądami)."""
    return (
        merchants.base_merchant(kind, description, counterparty),
        dictionary.match(merchants.source_text(kind, description, counterparty)),
    )


_FACT_COLUMNS = "id, account_id, kind, amount, description, counterparty_name, counterparty_account"


def _facts(t: sqlite3.Row, dictionary: Dictionary) -> tuple[Facts, merchants.Entry | None]:
    kind = str(t["kind"])
    base, entry = _derive(dictionary, kind, t["description"], t["counterparty_name"])
    facts = Facts(
        account_id=int(t["account_id"]),
        kind=kind,
        amount=Decimal(t["amount"]),
        merchant=entry.name if entry and entry.name else base,
        description=t["description"] or "",
        counterparty_name=t["counterparty_name"] or "",
        counterparty_account=t["counterparty_account"] or "",
    )
    return facts, entry


def facts(
    conn: sqlite3.Connection, ids: Collection[int], dictionary: Dictionary | None = None
) -> dict[int, Facts]:
    """Pola widziane przez reguły dla wybranych transakcji (np. pozycji kolejki) — bez
    przeliczania całej księgi."""
    d = dictionary or merchants.builtin()
    out: dict[int, Facts] = {}
    wanted = sorted(set(ids))
    for start in range(0, len(wanted), 500):
        chunk = wanted[start : start + 500]
        rows = conn.execute(
            f"SELECT {_FACT_COLUMNS} FROM txn WHERE id IN ({','.join('?' * len(chunk))})", chunk
        )
        for t in rows:
            out[int(t["id"])] = _facts(t, d)[0]
    return out


def _load(conn: sqlite3.Connection, dictionary: Dictionary) -> list[_Txn]:
    out = []
    rows = conn.execute(
        f"SELECT {_FACT_COLUMNS}, tx_date, booking_date, transfer_group, refund_of, "
        "category_id, category_source, rule_id, merchant FROM txn ORDER BY id"
    )
    for t in rows:
        known, entry = _facts(t, dictionary)
        out.append(
            _Txn(
                id=int(t["id"]),
                date=str(t["tx_date"] or t["booking_date"] or ""),
                amount=known.amount,
                facts=known,
                entry=entry,
                transfer=t["transfer_group"] is not None,
                refund_of=t["refund_of"],
                current=Assignment(
                    t["category_id"], t["category_source"], t["rule_id"], t["merchant"] or ""
                ),
                is_manual=t["category_source"] == "manual",
            )
        )
    return out


class _RuleIndex:
    """Pierwsza pasująca reguła bez sprawdzania wszystkich po kolei.

    Reguła z warunkiem „sprzedawca równa się X” (domyślna z kolejki) może pasować tylko do
    transakcji sprzedawcy X — trafia do słownika po znormalizowanej nazwie; reszta reguł jest
    sprawdzana po kolei, ale tylko te wyżej na liście niż kandydat ze słownika. Wynik jak przy
    sprawdzaniu wszystkich reguł po kolei, koszt prawie niezależny od liczby reguł."""

    def __init__(self, rules: Sequence[Rule]) -> None:
        self.by_merchant: dict[str, list[tuple[int, Rule]]] = {}
        self.rest: list[tuple[int, Rule]] = []
        for pos, r in enumerate(r for r in rules if r.enabled):
            key = next(
                (
                    _norm(c.field, c.value)
                    for c in r.conditions.text
                    if c.field == "merchant" and c.op == "equals"
                ),
                None,
            )
            if key is None:
                self.rest.append((pos, r))
            else:
                self.by_merchant.setdefault(key, []).append((pos, r))

    def first(self, facts: Facts) -> Rule | None:
        found = next(
            (
                (pos, r)
                for pos, r in self.by_merchant.get(_norm("merchant", facts.merchant), ())
                if r.conditions.matches(facts)
            ),
            None,
        )
        for pos, r in self.rest:
            if found is not None and pos > found[0]:
                break
            if r.conditions.matches(facts):
                return r
        return found[1] if found else None


def _classify(
    txns: Sequence[_Txn], rules: Sequence[Rule], slugs: dict[str, int]
) -> dict[int, Assignment]:
    index = _RuleIndex(rules)
    found: dict[int, tuple[Rule | None, str, learn.Key]] = {}
    decided: dict[learn.Key, list[int]] = defaultdict(list)
    for t in txns:
        rule = index.first(t.facts)
        merchant = (rule.rename if rule and rule.rename else None) or t.facts.merchant
        key: learn.Key = (merchant, review.direction(t.amount))
        found[t.id] = (rule, merchant, key)
        if t.is_manual and t.current.category_id is not None and merchant:
            decided[key].append(t.current.category_id)
    memory = {key: learn.memory(cats, 1) for key, cats in decided.items()}  # pamięć sprzedawcy
    result: dict[int, Assignment] = {}
    for t in txns:
        rule, merchant, key = found[t.id]
        if t.is_manual:
            result[t.id] = Assignment(t.current.category_id, "manual", None, merchant)
        elif t.transfer:
            result[t.id] = Assignment(None, None, None, merchant)
        elif rule is not None:
            result[t.id] = Assignment(rule.category_id, "rule", rule.id, merchant)
        elif t.entry is not None and t.entry.slug in slugs:
            result[t.id] = Assignment(slugs[t.entry.slug], "dictionary", None, merchant)
        elif (slug := KIND_DEFAULTS.get(t.facts.kind)) and slug in slugs:
            result[t.id] = Assignment(slugs[slug], "kind", None, merchant)
        elif (learned := memory.get(key)) is not None:
            result[t.id] = Assignment(learned, "learned", None, merchant)
        else:
            result[t.id] = Assignment(None, None, None, merchant)
    for t in txns:  # zwroty po zakupach: dziedziczą końcową kategorię zakupu
        if t.refund_of is None or t.is_manual or t.transfer:
            continue
        purchase = result.get(t.refund_of)
        if purchase is not None and purchase.category_id is not None:
            result[t.id] = replace(
                result[t.id], category_id=purchase.category_id, source="refund", rule_id=None
            )
    return result


def _slugs(conn: sqlite3.Connection) -> dict[str, int]:
    return {c.slug: c.id for c in taxonomy.leaves(conn).values()}


def recategorize(conn: sqlite3.Connection, dictionary: Dictionary | None = None) -> int:
    """Przelicz kategorie i sprzedawców wszystkich transakcji; zwraca liczbę zmienionych."""
    txns = _load(conn, dictionary or merchants.builtin())
    result = _classify(txns, all_rules(conn), _slugs(conn))
    changed = 0
    for t in txns:
        new = result[t.id]
        if new != t.current:
            conn.execute(
                "UPDATE txn SET category_id = ?, category_source = ?, rule_id = ?, merchant = ? "
                "WHERE id = ?",
                (new.category_id, new.source, new.rule_id, new.merchant, t.id),
            )
            changed += 1
    hits = Counter(a.rule_id for a in result.values() if a.rule_id is not None)
    for rid, n in conn.execute("SELECT id, hits FROM rule").fetchall():
        if hits.get(rid, 0) != n:
            conn.execute("UPDATE rule SET hits = ? WHERE id = ?", (hits.get(rid, 0), rid))
    return changed


@dataclass(frozen=True)
class Sample:
    txn_id: int
    date: str
    amount: Decimal
    merchant: str
    category_now: int | None
    category_new: int | None
    note: str  # „ręczna” / „wcześniejsza reguła” / „zwrot” / ""


@dataclass
class Preview:
    matches: int = 0  # transakcje spełniające warunki (bez przelewów wewnętrznych)
    total: Decimal = Decimal(0)  # suma ich kwot
    applied: int = 0  # dostaną kategorię z tej reguły
    changes: int = 0  # zmiana kategorii w całej księdze po zapisie
    manual_skipped: int = 0  # pasują, ale mają ręczną kategorię
    shadowed: int = 0  # pasują, ale wygrywa wcześniejsza reguła
    samples: list[Sample] = field(default_factory=list)


def preview(
    conn: sqlite3.Connection,
    rule: Rule,
    dictionary: Dictionary | None = None,
    *,
    release: int | None = None,
    release_any: bool = False,
) -> Preview:
    """Skutek zapisania reguły (nowej na górze listy albo edytowanej w miejscu).

    `release` — transakcja, z której poprawki powstaje reguła: jej ręczna kategoria równa
    kategorii reguły przejdzie pod regułę (`release_manual` przy zapisie); z `release_any` —
    niezależnie od kategorii (reguła z formularza kategorii na Transakcjach zdejmuje ręczną)."""
    candidate = replace(rule, id=rule.id if rule.id is not None else PREVIEW_ID, enabled=True)
    rules = all_rules(conn)
    if rule.id is None:
        rules = [candidate, *rules]
    else:
        rules = [candidate if r.id == rule.id else r for r in rules]
    txns = _load(conn, dictionary or merchants.builtin())
    for t in txns:
        if (
            t.id == release
            and t.is_manual
            and (release_any or t.current.category_id == rule.category_id)
        ):
            t.is_manual = False
    result = _classify(txns, rules, _slugs(conn))
    out = Preview()
    matched: list[tuple[_Txn, str]] = []
    for t in txns:
        new = result[t.id]
        if new.category_id != t.current.category_id:
            out.changes += 1
        if t.transfer or not candidate.conditions.matches(t.facts):
            continue
        out.matches += 1
        out.total += t.amount
        if new.rule_id == candidate.id:
            out.applied += 1
            note = ""
        elif t.is_manual:
            out.manual_skipped += 1
            note = "ręczna"
        elif new.source == "refund":
            note = "zwrot"
        else:
            out.shadowed += 1
            note = "wcześniejsza reguła"
        matched.append((t, note))
    matched.sort(key=lambda m: (m[0].date, m[0].id), reverse=True)
    out.samples = [
        Sample(
            txn_id=t.id,
            date=t.date,
            amount=t.amount,
            merchant=result[t.id].merchant,
            category_now=t.current.category_id,
            category_new=result[t.id].category_id,
            note=note,
        )
        for t, note in matched[:PREVIEW_SAMPLES]
    ]
    return out


def set_manual(conn: sqlite3.Connection, txn_id: int, category_id: int | None) -> None:
    """Ręczna kategoria transakcji; `None` przywraca kategorię automatyczną.

    Decyzja o pozycji z pamięci sprzedawcy liczy się w `LEARNED_STATS_KEY` jako potwierdzona (ta
    sama kategoria) albo poprawiona (inna) — trafność pamięci na żywo na ekranie Status.

    Po zmianie trzeba wywołać `recategorize` (zwroty dziedziczą kategorię zakupu)."""
    row = conn.execute(
        "SELECT transfer_group, category_id, category_source FROM txn WHERE id = ?", (txn_id,)
    ).fetchone()
    if row is None:
        raise taxonomy.TaxonomyError("Nie ma takiej transakcji.")
    if category_id is None:
        conn.execute(
            "UPDATE txn SET category_source = NULL WHERE id = ? AND category_source = 'manual'",
            (txn_id,),
        )
        return
    if row["transfer_group"] is not None:
        raise taxonomy.TaxonomyError("Przelew między własnymi kontami nie ma kategorii.")
    if category_id not in taxonomy.leaves(conn):
        raise taxonomy.TaxonomyError("Wybierz podkategorię.")
    if row["category_source"] == "learned":
        stats = learned_stats(conn)
        stats["confirmed" if row["category_id"] == category_id else "corrected"] += 1
        kv_set(conn, LEARNED_STATS_KEY, stats)
    conn.execute(
        "UPDATE txn SET category_id = ?, category_source = 'manual', rule_id = NULL WHERE id = ?",
        (category_id, txn_id),
    )


def learned_stats(conn: sqlite3.Connection) -> dict[str, int]:
    """Decyzje o pozycjach z pamięci sprzedawcy: {"confirmed": n, "corrected": n}."""
    stats: dict[str, int] = kv_get(conn, LEARNED_STATS_KEY) or {"confirmed": 0, "corrected": 0}
    return stats


def dictionary_hits(conn: sqlite3.Connection, dictionary: Dictionary | None = None) -> Counter[int]:
    """Liczba transakcji skategoryzowanych przez każdy wpis słownika (klucz: `Entry.order`)."""
    d = dictionary or merchants.builtin()
    hits: Counter[int] = Counter()
    for t in conn.execute(
        "SELECT kind, description, counterparty_name FROM txn WHERE category_source = 'dictionary'"
    ):
        _, entry = _derive(d, str(t["kind"]), t["description"], t["counterparty_name"])
        if entry is not None:
            hits[entry.order] += 1
    return hits


def release_manual(conn: sqlite3.Connection, txn_id: int, category_id: int) -> bool:
    """Ręczna kategoria równa kategorii nowej reguły → transakcja przechodzi pod regułę."""
    cur = conn.execute(
        "UPDATE txn SET category_source = NULL "
        "WHERE id = ? AND category_source = 'manual' AND category_id = ?",
        (txn_id, category_id),
    )
    return cur.rowcount > 0
