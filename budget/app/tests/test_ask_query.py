"""Język zapytań czatu (M12): walidacja planu, zgodność z „Wydatkami”, podział, prywatność."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from budget import spending
from budget.ask import query
from budget.ask.query import PlanError
from budget.categorize import engine, taxonomy

from .test_categorize_engine import add, conn, sid

__all__ = ["conn"]

TODAY = date(2026, 10, 6)


def plan(c: sqlite3.Connection, **kw: Any) -> query.Plan:
    raw: dict[str, Any] = {
        "unsupported": "",
        "periods": [{"from": "2026-09", "to": "2026-09"}],
        "scope": "expenses",
        "categories": [],
        "flex_groups": [],
        "text": "",
        "group_by": "none",
        "metric": "sum",
        "limit": 10,
        **kw,
    }
    return query.parse(raw, taxonomy.all_categories(c), TODAY)


def run(c: sqlite3.Connection, **kw: Any) -> query.Result:
    return query.execute(c, plan(c, **kw), TODAY)


@pytest.fixture
def month(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Ten sam miesiąc co `test_spending.test_sections_and_identity`."""
    buy = add(conn, "-100.00", "card", "LIDL XYZ POL 2026-09-02", day="2026-09-02")
    add(conn, "20.00", "card_refund", "LIDL XYZ POL 2026-09-05", day="2026-09-05", refund_of=buy)
    add(conn, "-60.00", "card", "ORLEN STACJA XYZ", day="2026-09-03")
    add(conn, "-40.00", "card", "SKLEP ABC XYZ", day="2026-09-04")
    add(conn, "5000.00", "transfer_in", "Pensja", "FIRMA X", day="2026-09-10")
    add(conn, "150.00", "transfer_in", "Zwrot", "JAN NOWAK", day="2026-09-11")
    sav = add(conn, "-1000.00", "transfer_out", "Lokata", "JA SAM", day="2026-09-12")
    big = add(conn, "-3000.00", "transfer_out", "Auto", "SALON", day="2026-09-13")
    add(conn, "-700.00", "card_repayment", "", None, day="2026-09-14", transfer_group="t1")
    add(conn, "-9.00", "card", "LIDL XYZ", day="2026-09-15", currency="EUR")
    engine.set_manual(conn, sav, sid(conn, "oszczednosci-przelewy"))
    engine.set_manual(conn, big, sid(conn, "jednorazowe"))
    engine.recategorize(conn)
    return conn


def test_totals_match_spending_screen(month: sqlite3.Connection) -> None:
    m = spending.build(month, date(2026, 9, 1), TODAY)
    for scope, expected in (
        ("expenses", m.expenses),
        ("income", m.income),
        ("savings", m.savings),
        ("excluded", m.excluded),
    ):
        assert run(month, scope=scope).periods[0].value == expected, scope
    res = run(month)
    assert res.periods[0].count == 4  # zwrot to osobna transakcja; spłata karty i EUR poza
    assert any("innej walucie: 1" in f for f in res.filters)


def test_group_by_category_levels(month: sqlite3.Connection) -> None:
    m = spending.build(month, date(2026, 9, 1), TODAY)
    mains = {r.label: r.values[0] for r in run(month, group_by="main_category").rows}
    for g in m.expense_groups:
        assert mains[g.category.name] == g.amount
    assert mains[query.NO_CATEGORY] == m.uncategorized_out
    leaves = run(month, group_by="category").rows
    assert leaves[0].values[0] == Decimal("80.00")  # spożywcze netto, największe pierwsze
    assert leaves[0].counts[0] == 2


def test_filters(month: sqlite3.Connection) -> None:
    food = sid(month, "spozywcze")
    main = taxonomy.all_categories(month)[food].parent_id
    assert run(month, categories=[main]).periods[0].value == Decimal("80.00")
    assert run(month, categories=[food], scope="income").periods[0].value == Decimal("80.00")
    assert run(month, text="orlen").periods[0].value == Decimal("60.00")
    assert run(month, text="lidl xyz").periods[0].count == 2
    assert run(month, flex_groups=["flexible"]).periods[0].value == Decimal("140.00")
    assert run(month, flex_groups=["fixed"]).periods[0].count == 0  # bez kategorii też poza
    with pytest.raises(PlanError):
        plan(month, categories=[99999])


def test_months_compare_and_metrics(conn: sqlite3.Connection) -> None:
    for day, amount in (
        ("2025-09-05", "-10.00"),
        ("2025-10-05", "-30.00"),
        ("2026-09-05", "-50.00"),
    ):
        add(conn, amount, "card", f"LIDL {day}", day=day)
    engine.recategorize(conn)
    res = run(
        conn,
        periods=[{"from": "2025-09", "to": "2025-10"}, {"from": "2026-09", "to": "2026-12"}],
        group_by="month",
    )
    assert [p.period.months for p in res.periods] == [2, 2]  # przyszłość przycięta do X 2026
    assert res.periods[1].partial and not res.periods[0].partial
    assert [r.label for r in res.rows] == [
        "wrzesień 2025 / wrzesień 2026",
        "październik 2025 / październik 2026",
    ]
    assert [r.values for r in res.rows] == [
        [Decimal("10.00"), Decimal("50.00")],
        [Decimal("30.00"), Decimal("0")],
    ]
    avg = run(conn, periods=[{"from": "2025-09", "to": "2025-10"}], metric="avg_per_month")
    assert avg.periods[0].value == Decimal("20.00")
    assert run(conn, periods=[{"from": "2025-01", "to": "2026-10"}], metric="count").periods[
        0
    ].value == Decimal(3)
    link = res.periods[1].link
    assert link == {"date_from": "2026-09-01", "date_to": "2026-10-06"}


@pytest.mark.parametrize(
    "kw",
    [
        {"periods": []},
        {"periods": [{"from": "2026-11", "to": "2026-12"}]},
        {"periods": [{"from": "2026-09", "to": "2026-08"}]},
        {"periods": [{"from": "2020-01", "to": "2026-01"}]},
        {"periods": [{"from": "wrzesień", "to": "2026-09"}]},
        {"group_by": "week"},
        {"flex_groups": ["income"]},
    ],
)
def test_invalid_plans(conn: sqlite3.Connection, kw: dict[str, Any]) -> None:
    with pytest.raises(PlanError):
        plan(conn, **kw)


def test_limit_clamped(conn: sqlite3.Connection) -> None:
    assert plan(conn, limit=-5).limit == 1 and plan(conn, limit=500).limit == query.MAX_LIMIT


def test_recipients_hidden_from_llm(conn: sqlite3.Connection) -> None:
    add(conn, "-200.00", "transfer_out", "Przelew A", "JXN QWERTOWSKI", day="2026-09-03")
    add(conn, "-100.00", "transfer_out", "Przelew B", "JXN QWERTOWSKI", day="2026-09-04")
    add(conn, "-50.00", "card", "QWERTYSHOP", day="2026-09-05")
    engine.recategorize(conn)
    res = run(conn, group_by="merchant")
    by_label = {r.llm_label: r for r in res.rows}
    assert by_label["[O1]"].label.upper() == "JXN QWERTOWSKI"
    assert by_label["[O1]"].values == [Decimal("300.00")]
    assert list(res.labels) == ["[O1]"]
    payload = json.dumps(res.for_llm(), ensure_ascii=False)
    assert "qwertowski" not in payload.lower() and "[O1]" in payload
    assert any("qwerty" in r.llm_label.lower() for r in res.rows)  # karta: nazwa wychodzi
