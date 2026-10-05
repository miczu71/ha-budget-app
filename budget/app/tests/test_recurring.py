"""Płatności cykliczne (M5b E1): detektor propozycji i przynależność transakcji do serii."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest

from budget.categorize.rules import Conditions, TextCondition
from budget.recurring import detect
from budget.recurring import series as S
from budget.storage import db
from budget.storage.db import now_iso

from .test_categorize_engine import add

TODAY = date(2026, 10, 2)


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = db.connect(":memory:")
    c.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (1, 'current', 'PLN', ?)",
        (now_iso(),),
    )
    yield c
    c.close()


def monthly(
    conn: sqlite3.Connection,
    name: str,
    amounts: list[str],
    *,
    last: date = date(2026, 9, 10),
    kind: str = "transfer_out",
    days: list[int] | None = None,
) -> list[int]:
    """Przelewy do `name`, raz w miesiącu, ostatni w miesiącu `last` (od najstarszego)."""
    ids = []
    n = len(amounts)
    for i, amount in enumerate(amounts):
        back = n - 1 - i
        y, m = divmod(last.year * 12 + last.month - 1 - back, 12)
        day = days[i] if days else last.day
        ids.append(
            add(conn, amount, kind, f"Opłata {i}", name, day=date(y, m + 1, day).isoformat())
        )
    return ids


def proposals(conn: sqlite3.Connection, today: date = TODAY) -> dict[str, detect.Proposal]:
    found = detect.find(S.candidates(conn), today, blocked=set(), covered=set())
    return {p.name: p for p in found}


def test_monthly_series_detected(conn: sqlite3.Connection) -> None:
    monthly(conn, "Qwertyflix Sp", ["-43.00", "-43.00", "-49.00", "-49.00", "-49.00"])
    [p] = proposals(conn).values()
    assert p.cadence == "M" and p.direction == "out" and p.occurrences == 5
    assert p.expected == Decimal("49.00")  # mediana ostatnich wystąpień
    assert p.tolerance == Decimal("6.00")  # rozrzut 6 > max(10%, 5 zł)
    assert p.anchor_day == 10
    assert p.conditions.text[0].op == "equals" and p.conditions.direction == "out"


def test_monthly_paid_on_different_days_of_month(conn: sqlite3.Connection) -> None:
    # 1., 7., 2., 8. dnia — odstępy 37, 25… dni, ale zawsze kolejny miesiąc
    monthly(conn, "Jxna Qwertowska", ["-2000.00"] * 4, last=date(2026, 9, 8), days=[1, 7, 2, 8])
    assert proposals(conn)["Jxna Qwertowska"].cadence == "M"


def test_quarterly_and_yearly(conn: sqlite3.Connection) -> None:
    for d in ("2026-01-15", "2026-04-15", "2026-07-15"):
        add(conn, "-120.00", "transfer_out", "Kwartał", "Zxcv Ubezpieczenia", day=d)
    for d in ("2024-11-20", "2025-11-21"):
        add(conn, "-300.00", "transfer_out", "Rok", "Asdf Domeny", day=d)
    found = proposals(conn)
    assert found["Zxcv Ubezpieczenia"].cadence == "Q"
    y = found["Asdf Domeny"]
    assert y.cadence == "Y" and y.occurrences == 2


def test_not_series(conn: sqlite3.Connection) -> None:
    # nieregularne odstępy
    for d in ("2026-06-01", "2026-06-09", "2026-08-20", "2026-09-02"):
        add(conn, "-50.00", "transfer_out", "Raz", "Nieregularny", day=d)
    # co miesiąc, ale zupełnie inne kwoty (zakupy u jednego sprzedawcy)
    monthly(conn, "Zakupowy", ["-20.00", "-310.00", "-75.00", "-150.00"])
    # seria, która ustała (ostatnio pół roku temu)
    monthly(conn, "Dawny", ["-10.00"] * 4, last=date(2026, 3, 5))
    # roczna z różną kwotą
    for d, a in (("2024-12-01", "-100.00"), ("2025-12-01", "-160.00")):
        add(conn, a, "transfer_out", "R", "Zmienny Roczny", day=d)
    assert proposals(conn) == {}


def test_income_and_bonus_does_not_widen_tolerance(conn: sqlite3.Connection) -> None:
    monthly(
        conn, "Firma Qwerty", ["8000.00", "8100.00", "30000.00", "8050.00", "8000.00", "8100.00"]
    )
    p = proposals(conn)["Firma Qwerty"]
    assert p.direction == "in" and p.cadence == "M"
    assert p.tolerance < Decimal("1000")


def test_income_expected_is_last_payout_not_median(conn: sqlite3.Connection) -> None:
    # wypłata po spadku (II próg): mediana 6 dałaby 8 150, a ostatnia to 7 000
    monthly(
        conn, "Firma Qwerty", ["9200.00", "9300.00", "7000.00", "6800.00", "6900.00", "7000.00"]
    )
    p = proposals(conn)["Firma Qwerty"]
    assert p.expected == Decimal("7000.00") and p.tolerance == Decimal("700.00")


def test_income_last_bonus_is_skipped_but_outflow_unchanged(conn: sqlite3.Connection) -> None:
    monthly(conn, "Firma Qwerty", ["7000.00", "7100.00", "6900.00", "7000.00", "30000.00"])
    assert proposals(conn)["Firma Qwerty"].expected == Decimal("7000.00")  # premia pominięta
    monthly(conn, "Czynsz Qwerty", ["-1000.00", "-1000.00", "-1200.00", "-1200.00", "-1200.00"])
    out = proposals(conn)["Czynsz Qwerty"]
    assert out.expected == Decimal("1200.00") and out.tolerance == Decimal("200.00")  # rozrzut


def test_loan_grouped_by_kind(conn: sqlite3.Connection) -> None:
    for i, d in enumerate(("2026-06-14", "2026-07-14", "2026-08-14", "2026-09-14")):
        add(conn, "-4800.00", "loan", f"Rata nr {i} kapitał {100 + i}", None, day=d)
    [p] = proposals(conn).values()
    assert p.name == detect.LOAN_NAME and p.conditions.kind == "loan"
    assert p.conditions.text == () and p.conditions.account_id == 1


def test_run_saves_and_does_not_repeat(conn: sqlite3.Connection) -> None:
    monthly(conn, "Qwertyflix Sp", ["-43.00"] * 4)
    monthly(conn, "Asdfify", ["-20.00"] * 4)
    assert len(detect.run(conn, TODAY)) == 2
    assert S.count_proposed(conn) == 2
    assert detect.run(conn, TODAY) == []  # grupy objęte seriami
    first = S.all_series(conn)[0]
    S.set_status(conn, first.id, "reject")
    assert detect.run(conn, TODAY) == []  # odrzucona nie wraca
    assert S.count_proposed(conn) == 1


def test_transfers_and_other_currency_ignored(conn: sqlite3.Connection) -> None:
    monthly(conn, "Wewnętrzny", ["-500.00"] * 4)
    conn.execute("UPDATE txn SET transfer_group = 'g1'")
    monthly(conn, "Walutowy", ["-9.99"] * 4)
    conn.execute("UPDATE txn SET currency = 'EUR' WHERE counterparty_name = 'Walutowy'")
    assert proposals(conn) == {}


def _series(conn: sqlite3.Connection, name: str, amount: str) -> int:
    conditions = Conditions(
        text=(TextCondition("counterparty_name", "equals", name),), direction="out"
    )
    return S.insert(
        conn,
        name=name,
        direction="out",
        cadence="M",
        conditions=conditions,
        expected=Decimal(amount),
        tolerance=Decimal("5"),
        anchor_day=10,
        status="active",
        origin="manual",
        key=None,
    )


def test_assign_closest_amount(conn: sqlite3.Connection) -> None:
    small = monthly(conn, "Gugle", ["-9.99"] * 3)
    big = monthly(conn, "Gugle", ["-59.99"] * 3, last=date(2026, 9, 12))
    a = _series(conn, "Gugle", "10.00")
    b = _series(conn, "Gugle", "60.00")
    members = S.assign(S.all_series(conn), S.candidates(conn))
    assert [t.id for t in members[a]] == small
    assert [t.id for t in members[b]] == big


def test_assign_skips_rejected_and_validates(conn: sqlite3.Connection) -> None:
    monthly(conn, "Gugle", ["-9.99"] * 3)
    sid = _series(conn, "Gugle", "10.00")
    conn.execute("UPDATE series SET status = 'rejected' WHERE id = ?", (sid,))
    assert S.assign(S.all_series(conn), S.candidates(conn)) == {}
    with pytest.raises(S.SeriesError, match="warunku tekstowego albo typu"):
        S.validate("X", "M", Conditions(direction="out"), Decimal(1), None)
    with pytest.raises(S.SeriesError, match="kierunek"):
        S.validate("X", "M", Conditions(kind="loan"), Decimal(1), None)
    with pytest.raises(S.SeriesError, match="kwotę"):
        S.validate("X", "M", Conditions(kind="loan", direction="out"), None, None)


def test_status_transitions(conn: sqlite3.Connection) -> None:
    sid = _series(conn, "Gugle", "10.00")
    assert S.set_status(conn, sid, "end").status == "ended"
    assert S.set_status(conn, sid, "restore").status == "active"
    with pytest.raises(S.SeriesError, match="aktywna"):
        S.set_status(conn, sid, "confirm")


def test_few_history_and_monthly_amount(conn: sqlite3.Connection) -> None:
    sid = _series(conn, "Gugle", "120.00")
    conn.execute("UPDATE series SET cadence = 'Y' WHERE id = ?", (sid,))
    s = S.get(conn, sid)
    assert s.monthly == Decimal("10.00")
    assert S.few_history(s, []) is True


def test_detector_speed_scale(conn: sqlite3.Connection) -> None:
    """Kilka tysięcy transakcji — detektor nie może blokować pętli panelu na długo."""
    start = date(2025, 1, 1)
    for i in range(3000):
        add(
            conn,
            f"-{10 + i % 97}.00",
            "card",
            f"Sklep {i % 300}",
            None,
            day=(start + timedelta(days=i % 600)).isoformat(),
        )
    import time

    t = time.perf_counter()
    detect.run(conn, TODAY)
    assert time.perf_counter() - t < 5
