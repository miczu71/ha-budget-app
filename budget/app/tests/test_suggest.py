"""Podpowiedzi AI (M4c): redakcja danych, prompt, walidacja, limity, zapis, pomiar."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from budget.categorize import engine as categorize
from budget.settings import Settings
from budget.storage import db
from budget.storage.db import now_iso
from budget.suggest import engine
from budget.suggest.client import AIError
from budget.suggest.redact import Txn, amount_range, describe, scrub, without_name

from .test_categorize_engine import add, sid

TODAY = date(2026, 10, 2)
AI = Settings(ai_base_url="http://router:3003/v1/", ai_api_key="k", ai_daily_calls=5)


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = db.connect(":memory:")
    c.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', ?)",
        (now_iso(),),
    )
    yield c
    c.close()


class Fake:
    """Atrapa `client.complete`: zapisuje prompty, odpowiada funkcją od listy pozycji."""

    def __init__(self, answer: Any = None, error: AIError | None = None) -> None:
        self.prompts: list[str] = []
        self.answer = answer or (lambda items: [])
        self.error = error

    async def __call__(self, **kw: Any) -> tuple[dict[str, Any], int]:
        self.prompts.append(kw["prompt"])
        assert kw["schema"] is engine.SCHEMA and kw["model"] == AI.ai_model
        assert kw["base_url"] == "http://router:3003/v1"  # bez końcowego „/”
        if self.error:
            raise self.error
        items = json.loads(
            kw["prompt"].split("Pozycje (JSON, pole i = numer):\n")[1].split("\n")[0]
        )
        return {"items": self.answer(items)}, 123


# --- redakcja -------------------------------------------------------------------------------


def test_scrub_removes_numbers_contacts_and_accounts() -> None:
    text = (
        "Faktura 2026/09/123456 PL61 1090 1014 0000 0712 1981 2874 jan@example.com "
        "tel. +48 600 100 200 kod 00-950 QWERTY 2026-09-01"
    )
    assert scrub(text) == "Faktura tel. kod QWERTY"


def test_without_name_ignores_case_and_diacritics() -> None:
    assert without_name("Za obiad Łukasz dzięki", "LUKASZ KOWALSKI") == "Za obiad dzięki"
    assert without_name("Kowalski czynsz", "Jan Kowalski", "Jan Kowalski") == "czynsz"
    # odmiana nazwiska w tytule
    assert without_name("Prezent dla Jxna Qwertowskiego", "JXN QWERTOWSKI") == "Prezent dla"


def test_amount_range() -> None:
    assert amount_range(Decimal("-12.50")) == "0–20 zł"
    assert amount_range(Decimal("100")) == "100–500 zł"
    assert amount_range(Decimal("-2500")) == "powyżej 2000 zł"


def test_describe_card_payment() -> None:
    txns = [
        Txn("card", Decimal("-30"), "QWERTY 12 XYZ CHE 2026-09-01", ""),
        Txn("card", Decimal("-40"), "QWERTY 12 XYZ CHE 2026-09-05", ""),
    ]
    d = describe("Qwerty", "out", txns)
    assert d["sprzedawca"] == "Qwerty" and d["kraj"] == "Szwajcaria"
    assert d["rodzaj"] == "płatność kartą" and d["kierunek"] == "wydatek"
    assert d["kwota"] == "20–100 zł" and d["liczba"] == 2
    assert d["opisy"] == ["QWERTY 12 XYZ CHE"]


def test_describe_transfer_never_sends_recipient() -> None:
    txns = [
        Txn("transfer_out", Decimal("-480"), "Prezent dla Jxna Testowskiego", "JXN TESTOWSKI"),
        Txn(
            "transfer_out",
            Decimal("-80"),
            "Testowski zwrot za bilety PL61109010140000071219812874",
            "JAN TESTOWSKI",
        ),
    ]
    d = describe("Jan Testowski", "out", txns)
    sent = json.dumps(d, ensure_ascii=False)
    assert "sprzedawca" not in d
    assert "Testowski" not in sent and "TESTOWSKI" not in sent and "1090" not in sent
    assert "480" not in sent and d["kwota"] == "100–500 zł"  # tylko przedział kwoty
    assert d["opisy"] == ["Prezent dla", "zwrot za bilety"]


# --- przebieg -------------------------------------------------------------------------------


def _seed(conn: sqlite3.Connection) -> dict[str, int]:
    ids = {
        "q1": add(conn, "-30.00", "card", "QWERTY 12 XYZ POL 2026-09-01", day="2026-09-01"),
        "q2": add(conn, "-20.00", "card", "QWERTY 12 XYZ POL 2026-09-05", day="2026-09-05"),
        "person": add(conn, "-480.00", "transfer_out", "Prezent", "JAN TESTOWSKI"),
        "salary": add(conn, "5000.00", "transfer_in", "Wynagrodzenie", "FIRMA ABC SP Z O O"),
        "lidl": add(conn, "-50.00", "card", "LIDL UL. X XYZ POL 2026-09-01"),  # słownik
    }
    categorize.recategorize(conn)
    return ids


def test_pending_groups_by_merchant_and_direction(conn: sqlite3.Connection) -> None:
    _seed(conn)
    groups = engine.pending_groups(conn)
    assert [(g.merchant, g.direction, len(g.txns)) for g in groups] == [
        ("Firma Abc Sp Z O O", "in", 1),
        ("Jan Testowski", "out", 1),
        ("Qwerty", "out", 2),
    ]


async def test_run_stores_validated_answers(conn: sqlite3.Connection) -> None:
    _seed(conn)
    leaf, income = sid(conn, "restauracje"), sid(conn, "wynagrodzenie")
    by_name = {"wpływ": income, "wydatek": income}  # wydatek z kategorią przychodu → odrzucona

    def answer(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for it in items:
            cid = leaf if it.get("sprzedawca") == "Qwerty" else by_name[it["kierunek"]]
            out.append({"i": it["i"], "candidates": [{"category_id": cid, "confidence": 1.7}]})
        return out

    fake = Fake(answer)
    res = await engine.run(conn, AI, TODAY, call=fake)
    assert (res.calls, res.stored, res.waiting, res.error) == (1, 3, 0, None)
    rows = {
        (r["merchant"], r["direction"]): (r["category_id"], r["confidence"], r["status"])
        for r in conn.execute("SELECT * FROM suggestion")
    }
    assert rows == {
        ("Qwerty", "out"): (leaf, 1.0, "pending"),
        ("Firma Abc Sp Z O O", "in"): (income, 1.0, "pending"),
        ("Jan Testowski", "out"): (None, 0.0, "pending"),
    }
    [prompt] = fake.prompts
    assert "Restauracje" in prompt and "Lidl →" in prompt  # kategorie i przykłady kartowe
    assert "Testowski" not in prompt and "TESTOWSKI" not in prompt and "Firma" not in prompt
    assert engine.usage(conn, TODAY)["calls"] == 1 and engine.usage(conn, TODAY)["tokens"] == 123
    # o te same grupy nie pytamy drugi raz
    again = await engine.run(conn, AI, TODAY, call=fake)
    assert again.calls == 0 and len(fake.prompts) == 1
    [c] = engine.candidates(conn, "Qwerty", "out")
    assert c.main.name == "Jedzenie" and c.label == "Jedzenie › Restauracje i kawiarnie"
    assert engine.candidates(conn, "Jan Testowski", "out") == []  # „nie wiadomo”
    assert engine.candidates(conn, "Qwerty", "in") == []
    assert engine.stats(conn) == {"pending": 2, "unknown": 1, "waiting": 0}


async def test_run_missing_and_bad_answers_are_unknown(conn: sqlite3.Connection) -> None:
    _seed(conn)
    bad = [{"i": 0, "candidates": [{"category_id": 999, "confidence": 0.9}]}, {"i": "x"}]
    res = await engine.run(conn, AI, TODAY, call=Fake(lambda items: bad))
    assert res.stored == 3
    assert (
        conn.execute("SELECT count(*) FROM suggestion WHERE category_id IS NULL").fetchone()[0] == 3
    )


async def test_run_disabled_limits_and_errors(conn: sqlite3.Connection) -> None:
    _seed(conn)
    fake = Fake()
    assert (await engine.run(conn, Settings(), TODAY, call=fake)).calls == 0
    zero = Settings(ai_base_url="http://router/v1", ai_daily_calls=0)
    assert (await engine.run(conn, zero, TODAY, call=fake)).calls == 0
    assert fake.prompts == []
    failing = Fake(error=AIError("router AI: HTTP 502 — provider_error"))
    res = await engine.run(conn, AI, TODAY, call=failing)
    assert res.calls == 1 and res.stored == 0 and "502" in (res.error or "")
    u = engine.usage(conn, TODAY)
    assert u["calls"] == 1 and "502" in u["last_error"]
    assert engine.usage(conn, date(2026, 10, 3))["calls"] == 0  # nowa doba
    assert engine.calls_left(conn, AI, TODAY) == 4


async def test_run_batches_within_max_calls(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(conn)
    monkeypatch.setattr(engine, "BATCH", 1)
    fake = Fake()
    res = await engine.run(conn, AI, TODAY, max_calls=2, call=fake)
    assert res.calls == 2 and res.waiting == 1
    assert '"kierunek": "wpływ"' in fake.prompts[0]  # największa kwota najpierw


async def test_evaluate_scores_against_known_categories(conn: sqlite3.Connection) -> None:
    ids = _seed(conn)
    categorize.set_manual(conn, ids["q1"], sid(conn, "restauracje"))
    categorize.set_manual(conn, ids["q2"], sid(conn, "restauracje"))
    categorize.recategorize(conn)
    truth = {"Qwerty": sid(conn, "restauracje"), "Lidl": sid(conn, "spozywcze")}

    def answer(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "i": it["i"],
                "candidates": [{"category_id": truth[it["sprzedawca"]], "confidence": 0.8}],
            }
            for it in items
        ]

    fake = Fake(answer)
    out = await engine.evaluate(conn, AI, TODAY, call=fake)
    assert out["n"] == 2 and out["own"]["n"] == 1 and out["dictionary"]["n"] == 1
    assert out["all"][0] == {"threshold": 0.0, "shown": 2, "leaf": 2, "main": 2, "top": 2}
    assert out["all"][3]["shown"] == 0  # pewność 0,8 < 0,9
    assert db.kv_get(conn, engine.EVAL_KEY)["n"] == 2
    # mierzeni sprzedawcy nie są przykładami w prompcie
    assert "Qwerty →" not in fake.prompts[0] and "Lidl →" not in fake.prompts[0]
    with pytest.raises(AIError):
        await engine.evaluate(conn, Settings(), TODAY, call=fake)


def test_parse_ranks_dedupes_and_validates(conn: sqlite3.Connection) -> None:
    from budget.categorize import taxonomy

    leaves = taxonomy.leaves(conn)
    r, s, d, inc = (sid(conn, x) for x in ("restauracje", "spozywcze", "ogrod", "wynagrodzenie"))
    g = engine.Group("Qwerty", "out")
    result = {
        "items": [
            {
                "i": 0,
                "candidates": [
                    {"category_id": s, "confidence": 0.3},
                    {"category_id": r, "confidence": 0.6},
                    {"category_id": s, "confidence": 0.5},  # powtórka — wyższa pewność
                    {"category_id": inc, "confidence": 0.9},  # przychód dla wydatku
                    {"category_id": 999, "confidence": 0.9},  # nie ma takiej
                    {"category_id": d, "confidence": 0.1},
                    {"category_id": "x"},
                ],
            }
        ]
    }
    [a] = engine.parse(result, [g], leaves)
    assert a.candidates == ((r, 0.6), (s, 0.5), (d, 0.1))
    assert a.category_id == r and a.confidence == 0.6
    [empty] = engine.parse({"items": []}, [g], leaves)
    assert empty.candidates == () and empty.category_id is None


async def test_decide_marks_accepted_or_rejected(conn: sqlite3.Connection) -> None:
    _seed(conn)
    r, s = sid(conn, "restauracje"), sid(conn, "spozywcze")

    def answer(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "i": it["i"],
                "candidates": [
                    {"category_id": r, "confidence": 0.7},
                    {"category_id": s, "confidence": 0.2},
                ],
            }
            for it in items
        ]

    await engine.run(conn, AI, TODAY, call=Fake(answer))
    assert [c.category.id for c in engine.candidates(conn, "Qwerty", "out")] == [r, s]
    engine.decide(conn, "Qwerty", "out", s)  # drugi kandydat też się liczy
    engine.decide(conn, "Firma Abc Sp Z O O", "in", sid(conn, "ogrod"))
    engine.decide(conn, "Nieznany", "out", s)  # bez podpowiedzi — nic
    status = dict(conn.execute("SELECT merchant, status FROM suggestion").fetchall())
    assert status["Qwerty"] == "accepted" and status["Firma Abc Sp Z O O"] == "rejected"
    assert engine.candidates(conn, "Qwerty", "out") == []  # zdecydowana — bez chipów
    assert engine.stats(conn)["accepted"] == 1 and engine.stats(conn)["rejected"] == 1


def test_score_counts_top_candidates(conn: sqlite3.Connection) -> None:
    from budget.categorize import taxonomy

    r, s = sid(conn, "restauracje"), sid(conn, "spozywcze")
    g = engine.Group("Qwerty", "out")
    g.known[r] += 1
    g.sources["rule"] += 1
    out = engine.score([engine.Answer(g, ((s, 0.8), (r, 0.4)))], taxonomy.all_categories(conn))
    assert out["all"][0] == {"threshold": 0.0, "shown": 1, "leaf": 0, "main": 1, "top": 1}


def test_migration_drops_pending_single_suggestions() -> None:
    from budget.storage.db import migrations

    names = [name for _, name, _ in migrations()]
    assert names[-1] == "005_suggestion_candidates.sql"
