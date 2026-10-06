"""Czat M12: przebieg pytanie → plan → wynik → odpowiedź z atrapą LLM; limit, log, prywatność."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from budget.ask import engine
from budget.categorize import engine as categorize
from budget.settings import Settings
from budget.suggest import engine as suggest
from budget.suggest.client import AIError

from .test_categorize_engine import add, conn

__all__ = ["conn"]

TODAY = date(2026, 10, 6)
PLAN = {
    "unsupported": "",
    "periods": [{"from": "2026-09", "to": "2026-09"}],
    "scope": "expenses",
    "categories": [],
    "flex_groups": [],
    "text": "",
    "group_by": "merchant",
    "metric": "sum",
    "limit": 10,
}


class FakeLLM:
    def __init__(self, *replies: dict[str, Any] | Exception) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    async def __call__(self, **kw: Any) -> tuple[dict[str, Any], int]:
        self.prompts.append(kw["prompt"])
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply, 7


def settings(tmp_path: Path, calls: int = 40) -> Settings:
    return Settings(
        config_dir=tmp_path, data_dir=tmp_path, ai_base_url="http://r/v1", chat_daily_calls=calls
    )


def data(c: sqlite3.Connection) -> None:
    add(c, "-200.00", "transfer_out", "Przelew A", "JXN QWERTOWSKI", day="2026-09-03")
    add(c, "-50.00", "card", "QWERTYSHOP", day="2026-09-05")
    categorize.recategorize(c)


async def test_full_flow_restores_names(conn: sqlite3.Connection, tmp_path: Path) -> None:
    data(conn)
    llm = FakeLLM(PLAN, {"answer": "Najwięcej poszło do [O1]: 200,00 zł."})
    a = await engine.ask(conn, settings(tmp_path), "  Komu płacimy najwięcej?  ", TODAY, llm)
    assert not a.error and not a.unsupported
    assert "qwertowski" in a.text.lower() and "[O1]" not in a.text
    assert a.result is not None and a.result.periods[0].value == 250
    # do modelu nie trafia nazwa osoby — ani w planie, ani w wyniku
    assert all("qwertowski" not in p.lower() for p in llm.prompts)
    assert "Komu płacimy najwięcej?" in llm.prompts[0] and "[O1]" in llm.prompts[1]
    assert suggest.usage(conn, TODAY, engine.USAGE_KEY)["calls"] == 2
    (entry,) = engine.history(conn)
    assert entry["q"] == "Komu płacimy najwięcej?" and entry["plan"]["group_by"] == "merchant"
    assert "value" not in str(entry)  # bez kwot


async def test_unsupported_uses_one_call(conn: sqlite3.Connection, tmp_path: Path) -> None:
    llm = FakeLLM({**PLAN, "unsupported": "brak sald kont"})
    a = await engine.ask(conn, settings(tmp_path), "Ile mam na koncie?", TODAY, llm)
    assert a.unsupported == "brak sald kont" and a.result is None
    assert suggest.usage(conn, TODAY, engine.USAGE_KEY)["calls"] == 1
    assert engine.history(conn)[0]["unsupported"] == "brak sald kont"


async def test_bad_plan_is_unsupported(conn: sqlite3.Connection, tmp_path: Path) -> None:
    llm = FakeLLM({**PLAN, "categories": [99999]})
    a = await engine.ask(conn, settings(tmp_path), "?", TODAY, llm)
    assert "nieznane kategorie" in a.unsupported and len(llm.prompts) == 1


async def test_limit_and_empty_question(conn: sqlite3.Connection, tmp_path: Path) -> None:
    llm = FakeLLM()
    a = await engine.ask(conn, settings(tmp_path, calls=1), "Ile?", TODAY, llm)
    assert "limit" in a.error and not llm.prompts
    assert (await engine.ask(conn, settings(tmp_path), "  ", TODAY, llm)).error == "Wpisz pytanie."


async def test_router_error(conn: sqlite3.Connection, tmp_path: Path) -> None:
    data(conn)
    llm = FakeLLM(PLAN, AIError("router AI: HTTP 502"))
    a = await engine.ask(conn, settings(tmp_path), "Komu?", TODAY, llm)
    assert a.error == "router AI: HTTP 502" and a.result is not None
    assert engine.history(conn)[0]["error"] == "router AI: HTTP 502"


def test_restore_exact_labels() -> None:
    labels = {"[O1]": "Osoba A", "[O10]": "Osoba B"}
    assert engine.restore("[O10] i [O1], [O2]", labels) == ("Osoba B i Osoba A, [O2]")
