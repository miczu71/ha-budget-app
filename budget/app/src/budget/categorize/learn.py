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
from budget.storage.db import kv_set, now_iso

EVAL_KEY = "learn_eval"
KS = (1, 2, 3)
THRESHOLDS = (0.8, 0.9, 0.95, 0.99)
LEARN_FROM = ("manual", "rule")
_MEMORY_FIELDS = (
    "txns",
    "txns_fired",
    "txns_correct",
    "decisions",
    "decisions_fired",
    "decisions_correct",
)

Key = tuple[str, str]  # (sprzedawca, kierunek)


@dataclass(frozen=True)
class _Row:
    month: str
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
        "t.category_id, t.category_source FROM txn t JOIN account a ON a.id = t.account_id "
        f"WHERE {review.QUEUE_SCOPE} ORDER BY day, t.id"
    )
    out = []
    for r in rows:
        amount, merchant = Decimal(r["amount"]), str(r["merchant"] or "")
        way, source = review.direction(amount), r["category_source"]
        learnable = source in LEARN_FROM and r["category_id"] is not None
        out.append(
            _Row(
                month=str(r["day"] or "")[:7],
                key=(merchant, way),
                category_id=r["category_id"],
                source=source,
                features=_features(merchant, str(r["kind"]), way, amount) if learnable else (),
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
    mem = {k: Counter(dict.fromkeys(_MEMORY_FIELDS, 0)) for k in KS}
    nb, seen = _NaiveBayes(), set[Key]()
    nb_n, nb_rows = 0, {t: Counter({"shown": 0, "correct": 0}) for t in THRESHOLDS}
    for month in _months(rows):
        decisions: dict[Key, list[tuple[_Row, int]]] = defaultdict(list)
        for r in month:
            if (cat := r.decided) is not None:
                decisions[r.key].append((r, cat))
        for key, decided in decisions.items():
            cats = [cat for _, cat in decided]
            for k in KS:
                guess = memory(history[key], k)
                c = mem[k]
                c["txns"] += len(cats)
                c["decisions"] += 1
                if guess is not None:
                    c["txns_fired"] += len(cats)
                    c["txns_correct"] += sum(cat == guess for cat in cats)
                    c["decisions_fired"] += 1
                    c["decisions_correct"] += all(cat == guess for cat in cats)
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
        "memory": [{"k": k, **mem[k]} for k in KS],
        "nb": {"n": nb_n, "rows": [{"threshold": t, **c} for t, c in nb_rows.items()]},
    }


def queue_share(conn: sqlite3.Connection, rows: Sequence[_Row]) -> dict[str, Any]:
    """Dzisiejsza kolejka (grupy jak na ekranie): ile ma już ręczne decyzje i co pamięć by
    przypisała (`fired`: k → pozycje)."""
    history: dict[Key, list[int]] = defaultdict(list)
    for r in rows:
        if (cat := r.decided) is not None:
            history[r.key].append(cat)
    groups = review.all_groups(conn)
    keys = [[(i.merchant, review.direction(i.amount)) for i in g.items] for g in groups]
    return {
        "txns": sum(len(g) for g in keys),
        "groups": len(groups),
        "known_txns": sum(1 for g in keys for key in g if history.get(key)),
        "known_groups": sum(1 for g in keys if any(history.get(key) for key in g)),
        "fired": {
            k: sum(1 for g in keys for key in g if memory(history.get(key, []), k) is not None)
            for k in KS
        },
    }


async def evaluate(conn: sqlite3.Connection) -> dict[str, Any]:
    """Pełny pomiar (obliczenia poza pętlą zdarzeń); wynik zapisany w `kv` (`EVAL_KEY`)."""
    rows = _rows(conn)
    measured = await asyncio.to_thread(backtest, rows)
    queue = queue_share(conn, rows)
    fired = queue.pop("fired")
    for row in measured["memory"]:
        row["queue_txns"] = fired[row["k"]]
    result = {"at": now_iso(), "months": len({r.month for r in rows}), **measured, "queue": queue}
    kv_set(conn, EVAL_KEY, result)
    return result
