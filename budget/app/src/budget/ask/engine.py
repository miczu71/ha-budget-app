"""Czat z danymi (M12, decyzja 23): pytanie → plan (LLM) → wynik lokalnie → odpowiedź (LLM).

Do LLM idzie: pytanie, lista kategorii, miesiąc początku danych, a w drugim wywołaniu wynik
zbiorczy po redakcji (`Result.for_llm`). Pojedyncze transakcje nie wychodzą; etykiety `[O1]`
w odpowiedzi podmieniane są na prawdziwe nazwy lokalnie.

Licznik wywołań jak w podpowiedziach (`suggest.engine.metered_call`), ale pod własnym kluczem
i z limitem `Settings.chat_daily_calls`; log ostatnich pytań (bez kwot) w `kv` — do przeglądu
na checkpoincie i rozszerzeń języka (E3).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from budget import flex
from budget.ask import query
from budget.ask.query import PlanError, Result
from budget.categorize import taxonomy
from budget.categorize.taxonomy import Category
from budget.settings import Settings
from budget.storage.db import kv_get, kv_set, now_iso
from budget.suggest import client
from budget.suggest import engine as suggest
from budget.suggest.client import AIError

log = logging.getLogger(__name__)

USAGE_KEY = "ask_usage"
LOG_KEY = "ask_log"
LOG_MAX = 100
CALLS_PER_QUESTION = 2
CONTEXT_MAX = 4  # tur rozmowy przekazywanych modelowi (E2)
PLAN_JSON_MAX = 2000  # znaków planu w kontekście od klienta
QUESTION_MAX = 500
ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


@dataclass
class Answer:
    question: str
    text: str = ""  # odpowiedź z prawdziwymi nazwami
    result: Result | None = None
    unsupported: str = ""  # „nie umiem” — czego brakuje
    error: str = ""
    plan: dict[str, Any] | None = None  # surowy plan od LLM (do logu)
    context: list[dict[str, Any]] = field(default_factory=list)  # tury rozmowy po tej odpowiedzi
    turn: int = 1  # numer pytania w rozmowie (do logu)


def compact(plan: dict[str, Any]) -> dict[str, Any]:
    """Plan bez pustych pól — tyle wystarczy do kontekstu rozmowy (prompt i pole formularza)."""
    return {k: v for k, v in plan.items() if v not in ("", [], None) and k != "unsupported"}


def parse_context(raw: str | None) -> list[dict[str, Any]]:
    """Kontekst rozmowy z ukrytego pola formularza — dane od klienta: sprawdzane, zły → pusty."""
    try:
        items = json.loads(raw or "[]")
    except ValueError:
        return []
    if not isinstance(items, list):
        return []
    return [
        {"q": t["q"][:QUESTION_MAX], "plan": t["plan"]}
        for t in items[-CONTEXT_MAX:]
        if isinstance(t, dict)
        and isinstance(t.get("q"), str)
        and isinstance(t.get("plan"), dict)
        and len(json.dumps(t["plan"])) <= PLAN_JSON_MAX
    ]


def enabled(settings: Settings) -> bool:
    return settings.ai_enabled and settings.chat_daily_calls > 0


def questions_left(conn: sqlite3.Connection, settings: Settings, today: date) -> int:
    used = int(suggest.usage(conn, today, USAGE_KEY).get("calls", 0))
    return max(settings.chat_daily_calls - used, 0) // CALLS_PER_QUESTION


def history(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Ostatnie pytania, od najnowszego."""
    return list(reversed(kv_get(conn, LOG_KEY) or []))


def log_rows(conn: sqlite3.Connection, limit: int = 30) -> list[dict[str, Any]]:
    """Ostatnie wpisy logu do karty na Status (E3a), bez kwot: „jak policzono” zapisane przy
    pytaniu, „nie umiem” albo błąd."""
    rows = []
    for e in history(conn)[:limit]:
        if e.get("error"):
            outcome, detail = "error", f"błąd: {e['error']}"
        elif e.get("unsupported"):
            outcome, detail = "unsupported", f"nie umiem: {e['unsupported']}"
        else:
            outcome, detail = "ok", " · ".join(e.get("how") or ["—"])
        rows.append({**e, "turn": e.get("turn", 1), "outcome": outcome, "detail": detail})
    return rows


def _log(conn: sqlite3.Connection, a: Answer) -> None:
    entries = (kv_get(conn, LOG_KEY) or [])[-(LOG_MAX - 1) :]
    entries.append(
        {
            "at": now_iso(),
            "q": a.question,
            "turn": a.turn,
            "how": a.result.filters if a.result else None,
            "plan": a.plan,
            "unsupported": a.unsupported,
            "error": a.error,
        }
    )
    kv_set(conn, LOG_KEY, entries)


# --- prompty ---------------------------------------------------------------------------------


def category_lines(cats: dict[int, Category]) -> list[str]:
    lines = []
    for main in (c for c in cats.values() if c.is_main):
        lines.append(f"{main.id}: {main.name}")
        for c in (c for c in cats.values() if c.parent_id == main.id):
            lines.append(f"  {c.id}: {c.name} ({taxonomy.FLEX_LABELS.get(c.flex_group or '', '')})")
    return lines


def plan_prompt(
    question: str,
    categories: list[str],
    today: date,
    since: str,
    context: Sequence[dict[str, Any]] = (),
) -> str:
    plans = (json.dumps(t["plan"], ensure_ascii=False, separators=(",", ":")) for t in context)
    earlier = (
        [
            "Wcześniejsze pytania w tej rozmowie (od najstarszego) i ich plany",
            "(puste pola pominięte):",
            *(f"- {t['q']}\n  plan: {p}" for t, p in zip(context, plans, strict=True)),
            "Bieżące pytanie może się do nich odnosić (np. „a w 2025?”, „bez paliwa”, „rozbij na",
            "miesiące”) — wtedy weź ostatni plan i zmień w nim tylko to, o co prosi bieżące",
            "pytanie.",
            "",
        ]
        if context
        else []
    )
    return "\n".join(
        [
            "Tłumaczysz pytanie o domowy budżet na plan zapytania do bazy transakcji.",
            "Nie odpowiadasz na pytanie — zwracasz tylko plan (JSON).",
            f"Dzisiaj: {today.isoformat()} (bieżący miesiąc jest niepełny). Dane od: {since}.",
            "",
            "Pola planu:",
            "- periods: jeden okres albo dwa do porównania; miesiące RRRR-MM, oba końce włącznie.",
            "  „w tym roku” = od stycznia do bieżącego miesiąca; „w zeszłym roku” = cały poprzedni",
            "  rok; „ostatnie 12 miesięcy” = 12 pełnych miesięcy przed bieżącym. Pytanie bez",
            "  okresu = ostatnie 12 pełnych miesięcy.",
            "- scope: expenses (wydatki), income (wpływy), savings (odkładanie oszczędności),",
            "  excluded (poza budżetem, np. jednorazowe). Pomijane, gdy podasz categories.",
            "- categories: id kategorii głównych albo podkategorii z listy niżej; główna obejmuje",
            "  wszystkie swoje podkategorie. Pusta lista = cały zakres (scope).",
            "- exclude_categories: id kategorii (głównych albo podkategorii) do pominięcia, np.",
            "  „bez paliwa”; pusta lista = bez wykluczeń.",
            "- flex_groups: fixed (stałe), flexible (elastyczne), non_monthly (nieregularne) —",
            "  tylko wydatki; pusta lista = wszystkie.",
            "- text: fragment nazwy sprzedawcy, odbiorcy albo opisu (np. „orlen”), gdy pytanie",
            "  dotyczy konkretnego sprzedawcy, a nie kategorii; pusty = bez filtra.",
            "- group_by: none, month, category (podkategorie), main_category, merchant.",
            "- metric: sum (suma zł), count (liczba transakcji), avg_per_month (średnio na mies.).",
            "- limit: wierszy przy podziale na kategorie lub sprzedawców (domyślnie 10).",
            "- unsupported: pusty, gdy plan odpowiada na pytanie. Gdy pytania nie da się wyrazić",
            "  tymi polami (np. salda kont, prognoza, majątek, pojedyncza transakcja),",
            "  wpisz krótko po polsku, czego brakuje; resztę pól wypełnij czymkolwiek poprawnym.",
            "",
            "Wskazówki: „który miesiąc był najdroższy” → group_by month; „na co wydajemy",
            "najwięcej” → main_category; „ile kosztuje samochód” → kategorie związane",
            "z samochodem.",
            "",
            "Kategorie (id: kategoria główna, wcięte: podkategorie z grupą budżetu):",
            *categories,
            "",
            *earlier,
            f"Pytanie: {question}",
        ]
    )


def answer_prompt(question: str, payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Odpowiedz krótko (1–3 zdania, po polsku) na pytanie o domowy budżet na podstawie",
            "wyniku zapytania. Używaj wyłącznie liczb z wyniku; wolno policzyć tylko różnicę albo",
            "zmianę procentową między dwoma okresami. Nie zgaduj przyczyn, których nie widać",
            "w wyniku. Kwoty w formacie 1 234,56 zł. Etykiety w nawiasach kwadratowych (np. [O1])",
            "przepisuj bez zmian. Jeśli okres ma niepełny bieżący miesiąc, wspomnij o tym.",
            "Gdy transakcji jest 0, powiedz, że nie znaleziono pasujących transakcji.",
            "",
            "Wynik (JSON): metric sum = suma w zł, count = liczba transakcji, avg_per_month =",
            "średnio na miesiąc w zł; rows = podział, values = wartość dla każdego okresu;",
            "filters = jak policzono.",
            json.dumps(payload, ensure_ascii=False),
            "",
            f"Pytanie: {question}",
        ]
    )


def restore(text: str, labels: dict[str, str]) -> str:
    """`[O1]` → prawdziwa nazwa (lokalnie, po odpowiedzi LLM)."""
    for label, name in labels.items():
        text = text.replace(label, name)
    return text


# --- przebieg --------------------------------------------------------------------------------


async def _run(
    conn: sqlite3.Connection,
    settings: Settings,
    a: Answer,
    today: date,
    call: suggest.Call,
) -> None:
    cats = taxonomy.all_categories(conn)
    first = flex.first_month(conn)
    since = first.strftime("%Y-%m") if first else "—"
    a.plan = await suggest.metered_call(
        conn,
        settings,
        today,
        call,
        key=USAGE_KEY,
        prompt=plan_prompt(a.question, category_lines(cats), today, since, a.context),
        schema=query.SCHEMA,
        schema_name="zapytanie",
    )
    a.unsupported = str(a.plan.get("unsupported") or "").strip()
    if a.unsupported:
        return
    try:
        plan = query.parse(a.plan, cats, today)
    except (PlanError, TypeError, ValueError) as exc:
        a.unsupported = f"Nie udało się ułożyć zapytania ({exc})."
        return
    a.result = query.execute(conn, plan, today, cats)
    a.context = [*a.context, {"q": a.question, "plan": compact(a.plan)}][-CONTEXT_MAX:]
    raw = await suggest.metered_call(
        conn,
        settings,
        today,
        call,
        key=USAGE_KEY,
        prompt=answer_prompt(a.question, a.result.for_llm()),
        schema=ANSWER_SCHEMA,
        schema_name="odpowiedz",
    )
    a.text = restore(str(raw.get("answer") or "").strip(), a.result.labels)


async def ask(
    conn: sqlite3.Connection,
    settings: Settings,
    question: str,
    today: date,
    call: suggest.Call = client.complete,
    context: Sequence[dict[str, Any]] = (),
) -> Answer:
    """`context` — wcześniejsze tury rozmowy (`parse_context`); `Answer.context` — po tej turze
    (bez zmian, gdy pytanie się nie udało, żeby można było je powtórzyć)."""
    a = Answer(
        question.strip()[:QUESTION_MAX], context=list(context)[-CONTEXT_MAX:], turn=len(context) + 1
    )
    if not a.question:
        a.error = "Wpisz pytanie."
        return a
    if questions_left(conn, settings, today) < 1:
        a.error = "Wyczerpany dzienny limit pytań (opcja chat_daily_calls)."
        return a
    try:
        await _run(conn, settings, a, today, call)
    except AIError as exc:
        log.warning("czat: %s", exc)
        a.error = str(exc)
    _log(conn, a)
    return a
