"""Pomiar M7: pamięć sprzedawcy, naive Bayes i udział kolejki — na księdze syntetycznej."""

from __future__ import annotations

import sqlite3

import pytest

from budget.categorize import engine, learn
from budget.service import Service
from budget.storage import db
from budget.storage.db import now_iso

from .test_categorize_engine import add, conn, sid
from .test_web import _client

__all__ = ["conn", "service"]
from .test_web import service


def manual(conn: sqlite3.Connection, desc: str, day: str, slug: str, amount: str = "-30.00") -> int:
    tid = add(conn, amount, "card", f"{desc} XYZ POL {day}", day=day)
    engine.recategorize(conn)
    engine.set_manual(conn, tid, sid(conn, slug))
    return tid


@pytest.mark.parametrize(
    ("history", "k", "expected"),
    [([], 1, None), ([7], 1, 7), ([7], 2, None), ([7, 7], 2, 7), ([7, 8, 7], 1, None)],
)
def test_memory_needs_k_consistent_decisions(
    history: list[int], k: int, expected: int | None
) -> None:
    assert learn.memory(history, k) == expected


def test_backtest_uses_only_earlier_months(conn: sqlite3.Connection) -> None:
    food = "restauracje"
    manual(conn, "QWERTY 1", "2026-07-03", food)
    manual(conn, "QWERTY 1", "2026-07-20", food)  # ten sam miesiąc: jeszcze bez pamięci
    manual(conn, "QWERTY 1", "2026-08-05", food)  # pamięć k=1 trafia
    manual(conn, "QWERTY 1", "2026-09-05", "dostawy-jedzenia")  # pamięć myli się, spójność pęka
    out = learn.backtest(learn._rows(conn))
    k1 = out["memory"][0]
    assert (k1["txns"], k1["txns_fired"], k1["txns_correct"]) == (4, 2, 1)
    assert (k1["decisions"], k1["decisions_fired"], k1["decisions_correct"]) == (3, 2, 1)
    k3 = out["memory"][2]
    assert k3["txns_fired"] == 1 and k3["txns_correct"] == 0  # 3 zgodne przed wrześniem


def test_naive_bayes_scores_only_new_merchants(conn: sqlite3.Connection) -> None:
    for suffix, day in (("A", "2026-07-01"), ("B", "2026-07-02"), ("C", "2026-07-03")):
        manual(conn, f"FARMQ{suffix}", day, "apteka")
        manual(conn, f"KINQX{suffix}", day, "kultura", "-45.00")
    manual(conn, "FARMQD", "2026-08-01", "apteka")  # nowy sprzedawca, podobna nazwa
    manual(conn, "FARMQA", "2026-08-02", "apteka")  # znany — nie liczy się do NB
    nb = learn.backtest(learn._rows(conn))["nb"]
    assert nb["n"] == 7  # 6 z lipca (model pusty) + 1 nowy z sierpnia
    first = nb["rows"][0]
    assert first["threshold"] == 0.8 and first["shown"] == first["correct"] == 1


async def test_queue_share_and_evaluate(conn: sqlite3.Connection) -> None:
    manual(conn, "QWERTY 1", "2026-08-05", "restauracje")
    add(conn, "-12.00", "card", "QWERTY 1 XYZ POL 2026-09-01", day="2026-09-01")
    add(conn, "-13.00", "card", "QWERTY 1 XYZ POL 2026-09-02", day="2026-09-02")
    add(conn, "-14.00", "card", "LKJHG 9 XYZ POL 2026-09-03", day="2026-09-03")
    engine.recategorize(conn)
    out = await learn.evaluate(conn)
    q = out["queue"]
    assert (q["txns"], q["groups"], q["known_txns"], q["known_groups"]) == (3, 2, 2, 1)
    assert [m["queue_txns"] for m in out["memory"]] == [2, 0, 0]
    assert out["months"] == 2
    assert db.kv_get(conn, learn.EVAL_KEY)["queue"] == q


async def test_status_measure_button(service: Service) -> None:
    service.conn.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', ?)",
        (now_iso(),),
    )
    manual(service.conn, "QWERTY 1", "2026-08-05", "restauracje")
    async with _client(service) as client:
        assert "Kolejka dziś" not in (await client.get("/status")).text
        await client.post("/learn/eval")
        page = (await client.get("/status")).text
    assert "Pomiar kategoryzacji: 1 miesięcy historii" in page
    assert "Kolejka dziś" in page and "Pamięć sprzedawcy" in page
