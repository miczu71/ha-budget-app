"""Śledzenie promocji (M22 E5): okres, warunki z księgi i ręczne, premia, rejestr."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from budget import card, invest, promo_track
from budget.settings import Settings
from budget.suggest.client import AIError

from .test_categorize_engine import add, conn

__all__ = ["conn"]

TODAY = date(2026, 10, 19)
D = Decimal


def offer(c: sqlite3.Connection, bank: str = "Millennium", months: int | None = 3) -> int:
    return invest.save_offer(
        c, "account", bank, "5", None, None, None if months is None else str(months), "", False
    )


def test_count_purchases_period_and_accounts(conn: sqlite3.Connection) -> None:
    add(conn, "-10.00", day="2026-10-19")
    add(conn, "-10.00", day="2026-10-25", account=2)
    add(conn, "-10.00", day="2026-11-19")
    add(conn, "-10.00", day="2026-12-01")  # poza okresem
    add(conn, "10.00", "card_refund", day="2026-10-20")
    add(conn, "-10.00", "blik", day="2026-10-20")
    assert card.count_purchases(conn, date(2026, 10, 19), date(2026, 11, 19)) == 3


def test_start_sets_period_and_ledger_only_for_millennium(conn: sqlite3.Connection) -> None:
    a, b = (
        promo_track.start(conn, offer(conn), TODAY),
        promo_track.start(conn, offer(conn, "Bank X", 2), TODAY),
    )
    by = {t.id: t for t in promo_track.tracks(conn)}
    assert by[a].end == date(2027, 1, 19) and by[b].end == date(2026, 12, 19)
    rows = {r["id"]: r["ledger"] for r in conn.execute("SELECT id, ledger FROM promo_track")}
    assert rows == {a: 1, b: 0}


def test_ledger_progress_for_payments_and_income(conn: sqlite3.Connection) -> None:
    tid = promo_track.start(conn, offer(conn), TODAY)
    promo_track.add_condition(conn, tid, "payments", "5 płatności kartą", "5")
    promo_track.add_condition(conn, tid, "income", "Wpływy 1000 zł", "1000")
    for day in ("2026-10-20", "2026-10-21", "2026-10-22"):
        add(conn, "-10.00", day=day)
    add(conn, "-10.00", day="2026-09-01")  # przed startem
    add(conn, "1200.00", "transfer_in", day="2026-10-25")
    (t,) = promo_track.tracks(conn)
    pay, inc = t.conditions
    assert pay.progress == D(3) and not pay.met
    assert inc.progress == D("1200.00") and inc.met
    assert not t.met
    add(conn, "-10.00", day="2026-10-23")
    add(conn, "-10.00", day="2026-10-24")
    assert promo_track.tracks(conn)[0].met


def test_other_bank_progress_is_manual(conn: sqlite3.Connection) -> None:
    tid = promo_track.start(conn, offer(conn, "Bank X"), TODAY)
    cid = promo_track.add_condition(conn, tid, "payments", "5 płatności", "5")
    add(conn, "-10.00", day="2026-10-20")
    (c,) = promo_track.tracks(conn)[0].conditions
    assert c.progress is None and not c.met
    promo_track.toggle_condition(conn, cid)
    assert promo_track.tracks(conn)[0].met


def test_condition_validation(conn: sqlite3.Connection) -> None:
    tid = promo_track.start(conn, offer(conn), TODAY)
    for args in (("zły", "x", None), ("manual", " ", None), ("payments", "x", None)):
        with pytest.raises(promo_track.PromoError):
            promo_track.add_condition(conn, tid, *args)
    with pytest.raises(promo_track.PromoError):
        promo_track.add_condition(conn, 999, "manual", "x")


def test_toggle_confirms_proposal(conn: sqlite3.Connection) -> None:
    tid = promo_track.start(conn, offer(conn), TODAY)
    cid = promo_track.add_condition(conn, tid, "manual", "Aplikacja", proposed=True)
    assert promo_track.tracks(conn)[0].conditions[0].proposed
    promo_track.toggle_condition(conn, cid)
    c = promo_track.tracks(conn)[0].conditions[0]
    assert c.done and not c.proposed


def test_remind_window(conn: sqlite3.Connection) -> None:
    tid = promo_track.start(conn, offer(conn, "Bank X", 1), TODAY)  # koniec 2026-11-19
    promo_track.add_condition(conn, tid, "manual", "Krok")
    (t,) = promo_track.tracks(conn)
    assert not t.remind(date(2026, 11, 1)) and t.remind(date(2026, 11, 12))
    assert not t.remind(date(2026, 11, 20))
    promo_track.toggle_condition(conn, t.conditions[0].id)
    assert promo_track.tracks(conn)[0].remind(date(2026, 11, 1))  # spełniona: odbierz premię


def test_mark_paid_to_asset_and_register(conn: sqlite3.Connection) -> None:
    tid = promo_track.start(conn, offer(conn, "Bank X"), TODAY)
    cid = promo_track.add_condition(conn, tid, "manual", "Krok")
    with pytest.raises(promo_track.PromoError):
        promo_track.mark_paid(conn, tid, "asset", TODAY)  # brak kwoty premii
    promo_track.set_bonus(conn, tid, "300")
    assert promo_track.register(conn) == (D("0.00"), D("0.00"))
    promo_track.toggle_condition(conn, cid)
    assert promo_track.register(conn) == (D("300.00"), D("0.00"))
    promo_track.mark_paid(conn, tid, "asset", TODAY)
    assert promo_track.register(conn) == (D("0.00"), D("300.00"))
    assert invest.assets_total(conn) == D("300.00")
    with pytest.raises(promo_track.PromoError):
        promo_track.mark_paid(conn, tid, "income", TODAY)


def test_mark_paid_to_income_creates_no_asset(conn: sqlite3.Connection) -> None:
    tid = promo_track.start(conn, offer(conn, "Bank X"), TODAY)
    promo_track.mark_paid(conn, tid, "income", TODAY)
    assert invest.assets_total(conn) == D("0.00")


def test_overdue_closes_unmet_only(conn: sqlite3.Connection) -> None:
    a = promo_track.start(conn, offer(conn, "Bank X", 1), TODAY)
    b = promo_track.start(conn, offer(conn, "Bank Y", 1), TODAY)
    promo_track.add_condition(conn, a, "manual", "Krok")
    cid = promo_track.add_condition(conn, b, "manual", "Krok")
    promo_track.toggle_condition(conn, cid)
    assert promo_track.overdue(conn, date(2026, 11, 20)) == 1
    st = {t.id: t.status for t in promo_track.tracks(conn)}
    assert st == {a: "failed", b: "active"}


# --- propozycja warunków (LLM) ---

AI = Settings(ai_base_url="http://router:3003/v1", ai_api_key="k", invest_daily_calls=3)


class Fake:
    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.result, self.prompts = result, []  # type: ignore[var-annotated]

    async def __call__(self, **kw: Any) -> tuple[dict[str, Any], int]:
        self.prompts.append(kw["prompt"])
        if self.result is None:
            raise AIError("limit")
        return self.result, 10


def track_with_text(
    c: sqlite3.Connection, text: str = "5 płatności kartą i 1000 zł wpływów"
) -> int:
    oid = invest.save_offer(c, "account", "Bank X", "5", None, None, "3", text, False)
    return promo_track.start(c, oid, TODAY)


async def test_propose_stores_validated_proposals(conn: sqlite3.Connection) -> None:
    tid = track_with_text(conn)
    fake = Fake(
        {
            "bonus": 300,
            "conditions": [
                {"kind": "payments", "label": " 5  płatności ", "target": 5},
                {"kind": "income", "label": "Wpływy", "target": 1000},
                {"kind": "manual", "label": "Aplikacja", "target": 0},
                {"kind": "payments", "label": "bez progu", "target": 0},  # odrzucona
                {"kind": "zły", "label": "x", "target": 1},  # odrzucona
            ],
        }
    )
    assert await promo_track.propose(conn, AI, TODAY, tid, fake) is None
    (t,) = promo_track.tracks(conn)
    assert t.bonus == D("300")
    assert [(c.kind, c.label, c.proposed) for c in t.conditions] == [
        ("payments", "5 płatności", True),
        ("income", "Wpływy", True),
        ("manual", "Aplikacja", True),
    ]
    assert "5 płatności kartą" in fake.prompts[0]


async def test_propose_failures_leave_track_without_conditions(conn: sqlite3.Connection) -> None:
    tid = track_with_text(conn)
    msg = await promo_track.propose(conn, AI, TODAY, tid, Fake(None))
    assert msg and "ręcznie" in msg
    off = await promo_track.propose(conn, Settings(), TODAY, tid, Fake({}))
    assert off and "wyłączone" in off
    empty = await promo_track.propose(conn, AI, TODAY, tid, Fake({"bonus": 0, "conditions": []}))
    assert empty and "ręcznie" in empty
    blank = await promo_track.propose(conn, AI, TODAY, track_with_text(conn, " "), Fake({}))
    assert blank and "opisu" in blank
    assert all(not t.conditions and t.bonus is None for t in promo_track.tracks(conn))
