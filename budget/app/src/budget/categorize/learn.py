"""Pomiar M7: ile pracy z kolejką zdjęłaby pamięć sprzedawcy albo klasyfikator (backtest).

Nic nie zmienia w księdze — wynik trafia tylko do `kv` (`EVAL_KEY`) dla ekranu Status.

Jednostką czasu jest miesiąc: kolejkę przegląda się miesiącami, a zapis w kolejce obejmuje naraz
całą grupę, więc decyzje z tego samego miesiąca nie podpowiadają sobie nawzajem. To ostrożne
przybliżenie — znacznika czasu decyzji w bazie nie ma, liczy się data transakcji.

- **Pamięć sprzedawcy:** kategoria, gdy (sprzedawca, kierunek) ma co najmniej k ręcznych decyzji
  i wszystkie są zgodne — sprzedawca z mieszanymi kategoriami (np. przelewy do jednej osoby na
  różne cele) nigdy nie jest przypisywany.
- **Naive Bayes:** słowa i trójki znaków nazwy sprzedawcy, typ, kierunek i rząd wielkości kwoty;
  uczony na decyzjach ręcznych i regułach, oceniany tylko na sprzedawcach widzianych pierwszy raz
  (tych pamięć z definicji nie obejmie).
"""

from __future__ import annotations

import asyncio
import math
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import groupby
from typing import Any

from budget import review
from budget.categorize import merchants
from budget.countries import card_origin
from budget.kinds import CARD_KINDS, TRANSFER_KINDS
from budget.storage.db import kv_set, now_iso

EVAL_KEY = "learn_eval"
KS = (1, 2, 3)
THRESHOLDS = (0.8, 0.9, 0.95, 0.99)
LEARN_FROM = ("manual", "rule")
_TXN_FIELDS = ("txns", "txns_fired", "txns_correct")
_DECISION_FIELDS = ("decisions", "decisions_fired", "decisions_correct")

Key = tuple[str, str]  # (sprzedawca, kierunek)

# Typy transakcji do rozbicia trafności pamięci (E1b): gdzie pamięć jest pewna, a gdzie nie
TYPE_LABELS = {
    "domestic": "Karta i BLIK w kraju",
    "abroad": "Karta za granicą",
    "transfers": "Przelewy",
    "other": "Inne",
}


def type_group(kind: str, description: str | None, orig_currency: str | None) -> str:
    if kind in CARD_KINDS:
        return "abroad" if card_origin(kind, description, orig_currency) else "domestic"
    return "transfers" if kind in TRANSFER_KINDS else "other"


@dataclass(frozen=True)
class _Row:
    id: int
    month: str
    group: str  # klucz `TYPE_LABELS`
    key: Key
    category_id: int | None
    source: str | None
    features: tuple[str, ...]  # tylko dla wierszy, z których uczy się klasyfikator

    @property
    def decided(self) -> int | None:
        """Ręczna decyzja u sprzedawcy z nazwą — bez nazwy nie ma czego zapamiętać."""
        return self.category_id if self.source == "manual" and self.key[0] else None


def _features(merchant: str, kind: str, way: str, amount: Decimal) -> tuple[str, ...]:
    words = merchants.words(merchant)
    feats = [f"w:{w}" for w in words if len(w) > 1]
    for w in words:
        padded = f"_{w}_"
        feats += [f"g:{padded[i : i + 3]}" for i in range(len(padded) - 2)]
    return (*feats, f"k:{kind}", f"d:{way}", f"a:{len(str(int(abs(amount))))}")


def _rows(conn: sqlite3.Connection) -> list[_Row]:
    rows = conn.execute(
        "SELECT coalesce(t.tx_date, t.booking_date) AS day, t.id, t.merchant, t.kind, t.amount, "
        "t.description, t.orig_currency, t.category_id, t.category_source "
        "FROM txn t JOIN account a ON a.id = t.account_id "
        f"WHERE {review.QUEUE_SCOPE} ORDER BY day, t.id"
    )
    out = []
    for r in rows:
        amount, merchant, kind = Decimal(r["amount"]), str(r["merchant"] or ""), str(r["kind"])
        way, source = review.direction(amount), r["category_source"]
        learnable = source in LEARN_FROM and r["category_id"] is not None
        out.append(
            _Row(
                id=int(r["id"]),
                month=str(r["day"] or "")[:7],
                group=type_group(kind, r["description"], r["orig_currency"]),
                key=(merchant, way),
                category_id=r["category_id"],
                source=source,
                features=_features(merchant, kind, way, amount) if learnable else (),
            )
        )
    return out


def memory(history: Sequence[int], k: int) -> int | None:
    """Kategoria z pamięci: co najmniej k decyzji, wszystkie zgodne."""
    return history[0] if len(history) >= k and len(set(history)) == 1 else None


class _NaiveBayes:
    def __init__(self) -> None:
        self.n = 0
        self.docs: Counter[int] = Counter()
        self.counts: dict[int, Counter[str]] = defaultdict(Counter)
        self.totals: Counter[int] = Counter()
        self.vocab: set[str] = set()

    def add(self, feats: Sequence[str], category_id: int) -> None:
        self.n += 1
        self.docs[category_id] += 1
        self.counts[category_id].update(feats)
        self.totals[category_id] += len(feats)
        self.vocab.update(feats)

    def predict(self, feats: Sequence[str]) -> tuple[int, float] | None:
        if not self.n:
            return None
        v = len(self.vocab) + 1
        scores = {
            c: math.log(d / self.n)
            + sum(math.log(self.counts[c][f] + 1) for f in feats)
            - len(feats) * math.log(self.totals[c] + v)
            for c, d in self.docs.items()
        }
        best = max(scores, key=scores.__getitem__)
        top = scores[best]
        return best, 1 / sum(math.exp(s - top) for s in scores.values())


def _months(rows: Iterable[_Row]) -> Iterable[list[_Row]]:
    for _, group in groupby(rows, key=lambda r: r.month):
        yield list(group)


def backtest(rows: Sequence[_Row]) -> dict[str, Any]:
    """Miesiąc po miesiącu: przewidywanie tylko z decyzji z wcześniejszych miesięcy."""
    history: dict[Key, list[int]] = defaultdict(list)
    dec = {k: Counter(dict.fromkeys(_DECISION_FIELDS, 0)) for k in KS}
    by_type = {(g, k): Counter(dict.fromkeys(_TXN_FIELDS, 0)) for g in TYPE_LABELS for k in KS}
    nb, seen = _NaiveBayes(), set[Key]()
    nb_n, nb_rows = 0, {t: Counter({"shown": 0, "correct": 0}) for t in THRESHOLDS}
    for month in _months(rows):
        decisions: dict[Key, list[tuple[_Row, int]]] = defaultdict(list)
        for r in month:
            if (cat := r.decided) is not None:
                decisions[r.key].append((r, cat))
        for key, decided in decisions.items():
            cats = [cat for _, cat in decided]
            per_type = Counter(r.group for r, _ in decided)
            for k in KS:
                dec[k]["decisions"] += 1
                for g, n in per_type.items():
                    by_type[g, k]["txns"] += n
                if (guess := memory(history[key], k)) is None:
                    continue
                dec[k]["decisions_fired"] += 1
                dec[k]["decisions_correct"] += all(cat == guess for cat in cats)
                for r, cat in decided:
                    by_type[r.group, k]["txns_fired"] += 1
                    by_type[r.group, k]["txns_correct"] += cat == guess
            if key not in seen:
                for r, cat in decided:
                    nb_n += 1
                    if (predicted := nb.predict(r.features)) is None:
                        continue
                    best, p = predicted
                    for t, c in nb_rows.items():
                        if p >= t:
                            c["shown"] += 1
                            c["correct"] += best == cat
            history[key] += cats
        for r in month:
            if r.features and r.category_id is not None:
                nb.add(r.features, r.category_id)
                seen.add(r.key)
    return {
        "memory": [
            {
                "k": k,
                **dec[k],
                **{f: sum(by_type[g, k][f] for g in TYPE_LABELS) for f in _TXN_FIELDS},
            }
            for k in KS
        ],
        "by_type": [
            {"group": g, "label": TYPE_LABELS[g], "k": k, **c}
            for (g, k), c in by_type.items()
            if c["txns"]
        ],
        "nb": {"n": nb_n, "rows": [{"threshold": t, **c} for t, c in nb_rows.items()]},
    }


def queue_share(conn: sqlite3.Connection, rows: Sequence[_Row]) -> dict[str, Any]:
    """Dzisiejsza kolejka (grupy jak na ekranie): ile ma już ręczne decyzje i co pamięć by
    przypisała (`fired`: (typ, k) → pozycje)."""
    history: dict[Key, list[int]] = defaultdict(list)
    for r in rows:
        if (cat := r.decided) is not None:
            history[r.key].append(cat)
    group_of = {r.id: r.group for r in rows if r.category_id is None}
    known_txns = known_groups = 0
    fired: Counter[tuple[str, int]] = Counter()
    groups = review.all_groups(conn)
    for g in groups:
        known = 0
        for i in g.items:
            past = history.get((i.merchant, review.direction(i.amount)), [])
            known += bool(past)
            for k in KS:
                if memory(past, k) is not None:
                    fired[group_of[i.id], k] += 1
        known_txns += known
        known_groups += bool(known)
    return {
        "txns": sum(g.count for g in groups),
        "groups": len(groups),
        "known_txns": known_txns,
        "known_groups": known_groups,
        "fired": fired,
    }


async def evaluate(conn: sqlite3.Connection) -> dict[str, Any]:
    """Pełny pomiar (obliczenia poza pętlą zdarzeń); wynik zapisany w `kv` (`EVAL_KEY`)."""
    rows = _rows(conn)
    measured = await asyncio.to_thread(backtest, rows)
    queue = queue_share(conn, rows)
    fired = queue.pop("fired")
    for row in measured["memory"]:
        row["queue_txns"] = sum(fired[g, row["k"]] for g in TYPE_LABELS)
    for row in measured["by_type"]:
        row["queue_txns"] = fired[row["group"], row["k"]]
    result = {"at": now_iso(), "months": len({r.month for r in rows}), **measured, "queue": queue}
    kv_set(conn, EVAL_KEY, result)
    return result
