"""Kolejka „Do przejrzenia” na księdze syntetycznej."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from decimal import Decimal

import pytest

from budget import review
from budget.categorize import engine
from budget.review import GroupKey
from budget.storage import db
from budget.storage.db import now_iso

from .test_categorize_engine import add, sid


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = db.connect(":memory:")
    now = now_iso()
    c.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', ?)",
        (now,),
    )
    c.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (2, 'card', 'PLN', ?)", (now,)
    )
    c.execute(
        "INSERT INTO account (id, kind, currency, include_in_budget, created_at) "
        "VALUES (3, 'current', 'PLN', 0, ?)",
        (now,),
    )
    yield c
    c.close()


def _seed(conn: sqlite3.Connection) -> dict[str, int]:
    ids = {
        "kebab1": add(conn, "-30.00", "card", "QWERTY 12 XYZ POL 2026-09-01", day="2026-09-01"),
        "kebab2": add(conn, "-20.00", "card", "QWERTY 12 XYZ POL 2026-09-05", day="2026-09-05"),
        "person_out": add(
            conn, "-500.00", "transfer_out", "Prezent", "JAN TESTOWSKI", day="2026-09-02"
        ),
        "person_in": add(conn, "100.00", "transfer_in", "Zwrot", "JAN TESTOWSKI", day="2026-09-03"),
        "abroad1": add(conn, "-80.00", "card", "ZXCVB 1 XyzCHE 2026-09-10", day="2026-09-10"),
        "abroad2": add(conn, "-40.00", "card", "ASDFG 2 XYZ CHE 2026-09-11", day="2026-09-11"),
        "fx": add(
            conn,
            "-60.00",
            "card",
            "Poiuy 3 Xyz",
            day="2026-09-12",
            account=2,
            orig_currency="EUR",
        ),
        "lidl": add(conn, "-50.00", "card", "LIDL UL. X XYZ POL 2026-09-01", day="2026-09-01"),
        "own": add(conn, "-700.00", "card_repayment", "", None, transfer_group="t1"),
        "pending": add(conn, "-15.00", "card", "QWERTY 12 XYZ POL 2026-09-06", status="PDNG"),
        "excluded": add(conn, "-99.00", "card", "QWERTY 12 XYZ POL 2026-09-07", account=3),
    }
    engine.recategorize(conn)
    return ids


def test_queue_groups_expenses(conn: sqlite3.Connection) -> None:
    ids = _seed(conn)
    q = review.queue(conn)
    assert [g.label for g in q.countries] == ["Szwajcaria", "Zagranica (EUR)"]
    assert [i.id for i in q.countries[0].items] == [ids["abroad2"], ids["abroad1"]]
    assert [(g.label, g.count, g.total) for g in q.merchants] == [
        ("Jan Testowski", 1, Decimal("500.00")),
        ("Qwerty", 2, Decimal("50.00")),
    ]
    kebab = q.merchants[1]
    assert (kebab.first_day, kebab.last_day) == ("2026-09-01", "2026-09-05")
    assert kebab.can_rule and not q.countries[0].can_rule
    # Lidl ze słownika, przelew własny, PDNG i konto poza budżetem — poza kolejką
    assert q.merchants_total == 2
    assert q.pending == 7  # 6 wydatków + 1 wpływ


def test_queue_incomes_and_sort(conn: sqlite3.Connection) -> None:
    _seed(conn)
    q = review.queue(conn, direction="in")
    assert [(g.label, g.key.direction) for g in q.merchants] == [("Jan Testowski", "in")]
    assert q.countries == []
    by_count = review.queue(conn, sort="count")
    assert [g.label for g in by_count.merchants] == ["Qwerty", "Jan Testowski"]
    assert review.queue(conn, limit=1).merchants_total == 2


def test_group_lookup_and_disappears_after_categorizing(conn: sqlite3.Connection) -> None:
    ids = _seed(conn)
    key = GroupKey("merchant", "Qwerty", "out", "PLN")
    g = review.group(conn, key)
    assert g is not None and {i.id for i in g.items} == {ids["kebab1"], ids["kebab2"]}
    engine.set_manual(conn, ids["kebab1"], sid(conn, "restauracje"))
    engine.set_manual(conn, ids["kebab2"], sid(conn, "restauracje"))
    engine.recategorize(conn)
    assert review.group(conn, key) is None
    assert review.pending_count(conn) == 5


def test_country_group_split_by_merchant(conn: sqlite3.Connection) -> None:
    _seed(conn)
    g = review.group(conn, GroupKey("country", "CHE", "out", "PLN"))
    assert g is not None
    assert [m for m, _ in g.merchants()] == ["Asdfg", "Zxcvb"]


def test_regular_foreign_merchant_is_merchant_group(conn: sqlite3.Connection) -> None:
    _seed(conn)
    for day in ("2026-06-03", "2026-07-03", "2026-08-03"):
        add(conn, "-9.99", "card", f"LKJHG 9 XYZ IRL {day}", day=day)
    engine.recategorize(conn)
    q = review.queue(conn)
    assert "Irlandia" not in [g.label for g in q.countries]  # subskrypcja, nie wyjazd
    lkjhg = next(g for g in q.merchants if g.label == "Lkjhg")
    assert lkjhg.count == 3 and lkjhg.can_rule
    # dwa miesiące to jeszcze wyjazd
    add(conn, "-5.00", "card", "MNBVC 1 XYZ AUT 2026-05-02", day="2026-05-02")
    add(conn, "-5.00", "card", "MNBVC 1 XYZ AUT 2026-06-02", day="2026-06-02")
    engine.recategorize(conn)
    assert "Austria" in [g.label for g in review.queue(conn).countries]


def test_pending_count_matches_queue(conn: sqlite3.Connection) -> None:
    _seed(conn)
    assert review.pending_count(conn) == review.queue(conn).pending == 7
    assert review.pending_count(db.connect(":memory:")) == 0
