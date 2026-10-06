"""Podpowiedzi kategorii z LLM: kto dostaje podpowiedź, prompt, walidacja, zapis, pomiar.

Jednostka = sprzedawca + kierunek (jak grupa kolejki „Do przejrzenia”); odpowiedź = do `TOP`
kandydatów (podkategoria + pewność), z których użytkownik wybiera sam (M4c, etap 3).
Przebieg (`run`) bierze grupy z kolejki bez podpowiedzi, od największej kwoty, paczkami po
`BATCH`, w limicie wywołań na dobę (`Settings.ai_daily_calls`). Pomiar (`evaluate`) pyta
o sprzedawców, którzy już mają kategorię (ręczną, z reguły albo ze słownika), i porównuje
odpowiedź z nią; przykłady w prompcie pomiaru nie zawierają mierzonych sprzedawców.

Do LLM trafia wyłącznie to, co zwraca `redact.describe`, lista kategorii użytkownika i
przykłady „sprzedawca kartowy → kategoria” — nigdy nazwy odbiorców przelewów.
"""

from __future__ import annotations

import json
import logging
import random
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from budget import ledger
from budget.categorize import taxonomy
from budget.categorize.taxonomy import Category
from budget.kinds import CARD_KINDS
from budget.review import PENDING_WHERE
from budget.settings import Settings
from budget.storage.db import kv_get, kv_set, now_iso
from budget.suggest import client
from budget.suggest.client import AIError
from budget.suggest.redact import Txn, describe

log = logging.getLogger(__name__)

BATCH = 40
TOP = 3
CALLS_PER_RUN = 3
EXAMPLES = 40
EVAL_SAMPLE = 80
THRESHOLDS = (0.0, 0.5, 0.7, 0.9)
USAGE_KEY = "ai_usage"
EVAL_KEY = "ai_eval"
SCHEMA_NAME = "kategorie"
FLEX_LABELS = {
    "income": "przychód",
    "fixed": "stałe",
    "flexible": "elastyczne",
    "non_monthly": "nieregularne",
    "savings": "oszczędności",
    "excluded": "poza budżetem",
}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "candidates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "category_id": {"type": "integer"},
                                "confidence": {"type": "number"},
                            },
                            "required": ["category_id", "confidence"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["i", "candidates"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

Call = Callable[..., Awaitable[tuple[dict[str, Any], int]]]


@dataclass
class Group:
    merchant: str
    direction: str
    txns: list[Txn] = field(default_factory=list)
    known: Counter[int] = field(default_factory=Counter)  # kategorie (pomiar)
    sources: Counter[str] = field(default_factory=Counter)

    @property
    def total(self) -> Decimal:
        return sum((abs(t.amount) for t in self.txns), Decimal(0))


@dataclass(frozen=True)
class Answer:
    group: Group
    candidates: tuple[tuple[int, float], ...] = ()  # od najpewniejszego; puste = nie wiadomo

    @property
    def category_id(self) -> int | None:
        return self.candidates[0][0] if self.candidates else None

    @property
    def confidence(self) -> float:
        return self.candidates[0][1] if self.candidates else 0.0


@dataclass
class RunResult:
    calls: int = 0
    stored: int = 0
    waiting: int = 0  # grupy bez podpowiedzi po przebiegu
    error: str | None = None


def _direction(amount: Decimal) -> str:
    return "out" if amount < 0 else "in"


def _groups(rows: Iterable[sqlite3.Row]) -> list[Group]:
    groups: dict[tuple[str, str], Group] = {}
    for r in rows:
        amount = Decimal(r["amount"])
        key = (str(r["merchant"]), _direction(amount))
        g = groups.setdefault(key, Group(*key))
        g.txns.append(
            Txn(
                kind=str(r["kind"]),
                amount=amount,
                description=str(r["description"] or ""),
                counterparty_name=str(r["counterparty_name"] or ""),
                orig_currency=r["orig_currency"],
            )
        )
        if r["category_id"] is not None:
            g.known[int(r["category_id"])] += 1
            g.sources[str(r["category_source"])] += 1
    return sorted(groups.values(), key=lambda g: (-g.total, g.merchant))


_COLUMNS = (
    "t.merchant, t.amount, t.kind, t.description, t.counterparty_name, t.orig_currency, "
    "t.category_id, t.category_source"
)


def pending_groups(conn: sqlite3.Connection) -> list[Group]:
    """Grupy kolejki, o które jeszcze nie pytano (odrzucona i „nie wiadomo” nie wracają)."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM txn t JOIN account a ON a.id = t.account_id "
        f"WHERE {PENDING_WHERE} AND coalesce(t.merchant, '') <> '' AND NOT EXISTS ("
        "SELECT 1 FROM suggestion s WHERE s.merchant = t.merchant AND s.direction = "
        "CASE WHEN t.amount LIKE '-%' THEN 'out' ELSE 'in' END)"
    )
    return _groups(rows)


def known_groups(conn: sqlite3.Connection) -> list[Group]:
    """Sprzedawcy z kategorią nadaną przez użytkownika albo słownik (do pomiaru)."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM txn t JOIN account a ON a.id = t.account_id "
        "WHERE t.status = 'BOOK' AND t.transfer_group IS NULL AND a.include_in_budget = 1 "
        "AND t.category_source IN ('manual', 'rule', 'dictionary') "
        "AND coalesce(t.merchant, '') <> ''"
    )
    return _groups(rows)


def category_lines(conn: sqlite3.Connection) -> list[str]:
    lines = []
    for main in taxonomy.tree(conn):
        for c in main.children:
            group = FLEX_LABELS.get(c.flex_group or "", "")
            lines.append(f"{c.id}: {main.category.name} › {c.name} ({group})")
    return lines


def examples(conn: sqlite3.Connection, exclude: set[str], limit: int = EXAMPLES) -> list[str]:
    """„sprzedawca → kategoria” z płatności kartą/BLIK (nazwy firm, nie osób)."""
    kinds = ", ".join(f"'{k}'" for k in sorted(CARD_KINDS))
    rows = conn.execute(
        "SELECT t.merchant, t.category_id, count(*) AS n, "
        "max(t.category_source IN ('manual', 'rule')) AS own FROM txn t "
        f"WHERE t.kind IN ({kinds}) AND t.category_source IN ('manual', 'rule', 'dictionary') "
        "AND coalesce(t.merchant, '') <> '' GROUP BY t.merchant, t.category_id "
        "ORDER BY own DESC, n DESC, t.merchant"
    ).fetchall()
    cats = taxonomy.all_categories(conn)
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        merchant = str(r["merchant"])
        if merchant in exclude or merchant in seen:
            continue
        seen.add(merchant)
        c = cats[int(r["category_id"])]
        parent = cats[c.parent_id].name if c.parent_id else ""
        out.append(f"{merchant} → {c.id}: {parent} › {c.name}")
        if len(out) >= limit:
            break
    return out


def build_prompt(categories: list[str], shots: list[str], items: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "Kategoryzujesz transakcje z polskiego konta osobistego do kategorii budżetu domowego.",
            f"Dla każdej pozycji podaj do {TOP} najbardziej prawdopodobnych podkategorii z listy",
            "(id i pewność 0–1), od najbardziej prawdopodobnej; różne podkategorie.",
            "Jeśli nie da się rozsądnie zgadnąć, podaj pustą listę kandydatów.",
            "Wydatek nie może dostać kategorii z grupy „przychód”.",
            "Pozycja to sprzedawca albo odbiorca z kilkoma opisami (dane częściowo wycięte).",
            "",
            "Kategorie (id: główna › podkategoria (grupa budżetu)):",
            *categories,
            "",
            "Przykłady kategorii nadanych przez użytkownika:" if shots else "",
            *shots,
            "",
            "Pozycje (JSON, pole i = numer):",
            json.dumps(items, ensure_ascii=False),
            "",
            'Odpowiedz JSON-em: {"items": [{"i": …, "candidates": [{"category_id": …, '
            '"confidence": …}, …]}]}, po jednej odpowiedzi na każdą pozycję.',
        ]
    )


def parse(result: dict[str, Any], batch: list[Group], leaves: dict[int, Category]) -> list[Answer]:
    """Odpowiedzi modelu → `Answer` dla każdej grupy paczki: kandydaci sprawdzeni (istniejąca
    podkategoria, wydatek ≠ przychód), bez powtórzeń, od najpewniejszego, najwyżej `TOP`."""
    got: dict[int, list[Any]] = {}
    for row in result.get("items") or []:
        try:
            got.setdefault(int(row["i"]), list(row["candidates"]))
        except (KeyError, TypeError, ValueError):
            continue
    answers = []
    for i, g in enumerate(batch):
        best: dict[int, float] = {}
        for cand in got.get(i, []):
            try:
                cid, conf = int(cand["category_id"]), float(cand["confidence"])
            except (KeyError, TypeError, ValueError):
                continue
            c = leaves.get(cid)
            if c is None or (g.direction == "out" and c.flex_group == "income"):
                continue
            best[cid] = max(best.get(cid, 0.0), min(max(conf, 0.0), 1.0))
        ranked = sorted(best.items(), key=lambda kv: -kv[1])[:TOP]
        answers.append(Answer(g, tuple(ranked)))
    return answers


# --- licznik wywołań ----------------------------------------------------------------------


def usage(conn: sqlite3.Connection, today: date, key: str = USAGE_KEY) -> dict[str, Any]:
    """Wywołania i tokeny dziś + ostatni błąd/sukces (stan w `kv`; `key` — czat M12 ma własny)."""
    u = kv_get(conn, key) or {}
    if u.get("day") != today.isoformat():
        u = {**u, "day": today.isoformat(), "calls": 0, "tokens": 0}
    return u


def _record(
    conn: sqlite3.Connection,
    today: date,
    tokens: int = 0,
    error: str | None = None,
    key: str = USAGE_KEY,
) -> None:
    u = usage(conn, today, key)
    u["calls"] = int(u.get("calls", 0)) + 1
    u["tokens"] = int(u.get("tokens", 0)) + tokens
    if error:
        u["last_error"], u["last_error_at"] = error, now_iso()
    else:
        u["last_ok_at"] = now_iso()
    kv_set(conn, key, u)


def calls_left(conn: sqlite3.Connection, settings: Settings, today: date) -> int:
    return max(settings.ai_daily_calls - int(usage(conn, today).get("calls", 0)), 0)


async def metered_call(
    conn: sqlite3.Connection,
    settings: Settings,
    today: date,
    call: Call,
    *,
    key: str = USAGE_KEY,
    prompt: str,
    schema: dict[str, Any],
    schema_name: str,
) -> dict[str, Any]:
    """Jedno wywołanie routera z zapisem w liczniku `key` (także nieudane — liczą się do limitu)."""
    try:
        result, tokens = await call(
            base_url=settings.ai_base_url,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            prompt=prompt,
            schema=schema,
            schema_name=schema_name,
        )
    except AIError as exc:
        _record(conn, today, error=str(exc), key=key)
        raise
    _record(conn, today, tokens, key=key)
    return result


async def _ask(
    conn: sqlite3.Connection,
    settings: Settings,
    today: date,
    batch: list[Group],
    shots: list[str],
    call: Call,
) -> list[Answer]:
    items = [{"i": i, **describe(g.merchant, g.direction, g.txns)} for i, g in enumerate(batch)]
    prompt = build_prompt(category_lines(conn), shots, items)
    result = await metered_call(
        conn, settings, today, call, prompt=prompt, schema=SCHEMA, schema_name=SCHEMA_NAME
    )
    return parse(result, batch, taxonomy.leaves(conn))


def _store(conn: sqlite3.Connection, answers: list[Answer], model: str) -> int:
    now = now_iso()
    with ledger.transaction(conn):
        for a in answers:
            conn.execute(
                "INSERT OR IGNORE INTO suggestion (merchant, direction, category_id, confidence, "
                "candidates, model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    a.group.merchant,
                    a.group.direction,
                    a.category_id,
                    a.confidence,
                    json.dumps(a.candidates),
                    model,
                    now,
                ),
            )
    return len(answers)


async def run(
    conn: sqlite3.Connection,
    settings: Settings,
    today: date,
    *,
    max_calls: int = CALLS_PER_RUN,
    call: Call = client.complete,
) -> RunResult:
    """Podpowiedzi dla grup kolejki bez podpowiedzi; błąd AI kończy przebieg (bez wyjątku)."""
    res = RunResult()
    if not settings.ai_enabled:
        return res
    groups = pending_groups(conn)
    shots = examples(conn, exclude=set())
    while groups and res.calls < max_calls and calls_left(conn, settings, today) > 0:
        batch, groups = groups[:BATCH], groups[BATCH:]
        res.calls += 1
        try:
            answers = await _ask(conn, settings, today, batch, shots, call)
        except AIError as exc:
            log.warning("Podpowiedzi AI: %s", exc)
            res.error = str(exc)
            break
        res.stored += _store(conn, answers, settings.ai_model)
    res.waiting = len(pending_groups(conn))
    if res.calls:
        log.info(
            "Podpowiedzi AI: wywołań %d, zapisanych %d, czeka %d",
            res.calls,
            res.stored,
            res.waiting,
        )
    return res


# --- pomiar trafności -----------------------------------------------------------------------


def _main_of(cats: dict[int, Category], cid: int | None) -> int | None:
    if cid is None or cid not in cats:
        return None
    return cats[cid].parent_id


def score(answers: list[Answer], cats: dict[int, Category]) -> dict[str, Any]:
    """Trafność wg progu pewności pierwszego kandydata (`leaf`/`main` — pierwszy kandydat,
    `top` — właściwa podkategoria wśród kandydatów), osobno dla kategorii użytkownika i słownika."""

    def table(rows: list[Answer]) -> list[dict[str, Any]]:
        out = []
        for t in THRESHOLDS:
            shown = [a for a in rows if a.category_id is not None and a.confidence >= t]
            truth = [a.group.known.most_common(1)[0][0] for a in shown]
            leaf = sum(a.category_id == k for a, k in zip(shown, truth, strict=True))
            main = sum(
                _main_of(cats, a.category_id) == _main_of(cats, k)
                for a, k in zip(shown, truth, strict=True)
            )
            top = sum(k in {c for c, _ in a.candidates} for a, k in zip(shown, truth, strict=True))
            out.append(
                {"threshold": t, "shown": len(shown), "leaf": leaf, "main": main, "top": top}
            )
        return out

    def is_own(a: Answer) -> bool:
        return a.group.sources["manual"] + a.group.sources["rule"] > 0

    own = [a for a in answers if is_own(a)]
    by_dict = [a for a in answers if not is_own(a)]
    return {
        "n": len(answers),
        "all": table(answers),
        "own": {"n": len(own), "rows": table(own)},
        "dictionary": {"n": len(by_dict), "rows": table(by_dict)},
    }


async def evaluate(
    conn: sqlite3.Connection,
    settings: Settings,
    today: date,
    *,
    sample: int = EVAL_SAMPLE,
    seed: int = 0,
    call: Call = client.complete,
) -> dict[str, Any]:
    """Pyta o próbkę sprzedawców z kategorią i zapisuje wynik w `kv` (`EVAL_KEY`)."""
    if not settings.ai_enabled:
        raise AIError("podpowiedzi AI wyłączone (opcja ai_base_url)")
    groups = known_groups(conn)
    random.Random(seed).shuffle(groups)
    # najpierw decyzje użytkownika (ręczne i reguły), potem słownik — do wielkości próbki
    groups.sort(key=lambda g: g.sources["manual"] + g.sources["rule"] == 0)
    chosen = groups[:sample]
    shots = examples(conn, exclude={g.merchant for g in chosen})
    answers: list[Answer] = []
    for start in range(0, len(chosen), BATCH):
        if calls_left(conn, settings, today) <= 0:
            raise AIError("wyczerpany dzienny limit wywołań AI")
        answers += await _ask(conn, settings, today, chosen[start : start + BATCH], shots, call)
    result = {
        "at": now_iso(),
        "model": settings.ai_model,
        **score(answers, taxonomy.all_categories(conn)),
    }
    kv_set(conn, EVAL_KEY, result)
    return result


# --- odczyt dla panelu ------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    category: Category
    main: Category
    confidence: float

    @property
    def label(self) -> str:
        return f"{self.main.name} › {self.category.name}"


def _candidates(row: sqlite3.Row, cats: dict[int, Category]) -> list[Candidate]:
    pairs = json.loads(row["candidates"]) if row["candidates"] else []
    if not pairs and row["category_id"] is not None:
        pairs = [[row["category_id"], row["confidence"]]]
    out = []
    for cid, conf in pairs:
        c = cats.get(int(cid))
        if c is not None and c.parent_id is not None:
            out.append(Candidate(c, cats[c.parent_id], float(conf)))
    return out


def candidates(conn: sqlite3.Connection, merchant: str, direction: str) -> list[Candidate]:
    """Kandydaci oczekującej podpowiedzi sprzedawcy (pusto: brak, „nie wiadomo”, zdecydowana)."""
    row = conn.execute(
        "SELECT candidates, category_id, confidence FROM suggestion "
        "WHERE merchant = ? AND direction = ? AND status = 'pending'",
        (merchant, direction),
    ).fetchone()
    return [] if row is None else _candidates(row, taxonomy.all_categories(conn))


def pending_candidates(conn: sqlite3.Connection, direction: str) -> dict[str, list[Candidate]]:
    """Kandydaci wszystkich oczekujących podpowiedzi w kierunku, po sprzedawcy (filtr kolejki)."""
    cats = taxonomy.all_categories(conn)
    rows = conn.execute(
        "SELECT merchant, candidates, category_id, confidence FROM suggestion "
        "WHERE direction = ? AND status = 'pending'",
        (direction,),
    )
    out = {str(r["merchant"]): _candidates(r, cats) for r in rows}
    return {m: c for m, c in out.items() if c}


def decide(conn: sqlite3.Connection, merchant: str, direction: str, category_id: int) -> None:
    """Użytkownik nadał kategorię sprzedawcy: podpowiedź przyjęta (to był kandydat) albo
    odrzucona (inna kategoria). Bez oczekującej podpowiedzi — nic."""
    row = conn.execute(
        "SELECT id, candidates, category_id FROM suggestion "
        "WHERE merchant = ? AND direction = ? AND status = 'pending'",
        (merchant, direction),
    ).fetchone()
    if row is None or row["category_id"] is None:
        return
    ids = {int(c) for c, _ in json.loads(row["candidates"] or "[]")} or {int(row["category_id"])}
    conn.execute(
        "UPDATE suggestion SET status = ?, decided_at = ? WHERE id = ?",
        ("accepted" if category_id in ids else "rejected", now_iso(), row["id"]),
    )


def stats(conn: sqlite3.Connection) -> dict[str, int]:
    """Podpowiedzi wg statusu + grupy kolejki z podpowiedzią i bez (karta „AI” na Status)."""
    counts: dict[str, int] = defaultdict(int)
    for r in conn.execute(
        "SELECT status, category_id IS NULL AS unknown, count(*) AS n FROM suggestion GROUP BY 1, 2"
    ):
        counts["unknown" if r["unknown"] else r["status"]] += int(r["n"])
    counts["waiting"] = len(pending_groups(conn))
    return dict(counts)
