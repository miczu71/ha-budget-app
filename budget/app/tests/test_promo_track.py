"""Śledzenie promocji (M22 E5): okres, warunki z księgi i ręczne, premia, rejestr."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from budget import card, inbox, invest, promo_track, summary
from budget.piggy import PiggyError
from budget.settings import Settings
from budget.snapshot import Snapshot
from budget.suggest.client import AIError

from .test_categorize_engine import add, conn

__all__ = ["conn"]

TODAY = date(2026, 10, 19)


@pytest.fixture(autouse=True)
def _millennium_accounts(conn: sqlite3.Connection) -> None:
    """Konta z EB mają nazwę banku („Bank Millennium”); licznik kart dopasowuje po niej."""
    conn.execute("UPDATE account SET bank = 'Bank Millennium'")


WAW = ZoneInfo("Europe/Warsaw")
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


def test_confirm_keeps_done_state(conn: sqlite3.Connection) -> None:
    tid = promo_track.start(conn, offer(conn), TODAY)
    cid = promo_track.add_condition(conn, tid, "manual", "Aplikacja", proposed=True)
    promo_track.confirm_condition(conn, cid)
    c = promo_track.tracks(conn)[0].conditions[0]
    assert not c.proposed and not c.done
    with pytest.raises(promo_track.PromoError):
        promo_track.confirm_condition(conn, 999)


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
    assert t.remind(date(2026, 11, 20))  # po terminie: do zamknięcia
    promo_track.toggle_condition(conn, t.conditions[0].id)
    assert promo_track.tracks(conn)[0].remind(date(2026, 11, 1))  # spełniona: odbierz premię


def test_mark_paid_to_asset_and_register(conn: sqlite3.Connection) -> None:
    tid = promo_track.start(conn, offer(conn, "Bank X"), TODAY)
    cid = promo_track.add_condition(conn, tid, "manual", "Krok")
    with pytest.raises(promo_track.PromoError):
        promo_track.mark_paid(conn, tid, "asset", TODAY)  # brak kwoty premii
    promo_track.set_bonus(conn, tid, "300")
    assert promo_track.register(promo_track.tracks(conn)) == (D("0.00"), D("0.00"))
    promo_track.toggle_condition(conn, cid)
    assert promo_track.register(promo_track.tracks(conn)) == (D("300.00"), D("0.00"))
    promo_track.mark_paid(conn, tid, "asset", TODAY)
    assert promo_track.register(promo_track.tracks(conn)) == (D("0.00"), D("300.00"))
    assert invest.assets_total(conn) == D("300.00")
    with pytest.raises(promo_track.PromoError):
        promo_track.mark_paid(conn, tid, "income", TODAY)


def test_mark_paid_to_income_creates_no_asset(conn: sqlite3.Connection) -> None:
    tid = promo_track.start(conn, offer(conn, "Bank X"), TODAY)
    promo_track.mark_paid(conn, tid, "income", TODAY)
    assert invest.assets_total(conn) == D("0.00")


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


# --- przypomnienia: dzwonek i push ---


def _active(c: sqlite3.Connection, months: int = 1) -> int:
    tid = promo_track.start(c, offer(c, "Bank X", months), TODAY)  # koniec 2026-11-19
    promo_track.add_condition(c, tid, "manual", "Aplikacja")
    promo_track.set_bonus(c, tid, "300")
    return tid


def bell(c: sqlite3.Connection, day: date) -> list[inbox.Item]:
    now = datetime(day.year, day.month, day.day, 8, tzinfo=WAW)
    return [
        i for i in inbox.items(Snapshot(c), now, inbox.BalanceMemo()) if i.kind == "promo_track"
    ]


def test_bell_unmet_met_and_overdue(conn: sqlite3.Connection) -> None:
    tid = _active(conn)
    assert bell(conn, date(2026, 11, 1)) == []
    (near,) = bell(conn, date(2026, 11, 14))
    assert near.severity == "warn" and "Aplikacja" in near.detail and "300\xa0zł" in near.detail
    (late,) = bell(conn, date(2026, 11, 25))
    assert "skończyła" in late.title
    promo_track.toggle_condition(conn, conn.execute("SELECT id FROM promo_condition").fetchone()[0])
    (ok,) = bell(conn, date(2026, 11, 1))
    assert ok.severity == "info" and "Odbierz premię" in ok.detail
    promo_track.mark_paid(conn, tid, "income", TODAY)
    assert bell(conn, date(2026, 11, 14)) == []


def test_push_only_unmet_on_remind_days_once(conn: sqlite3.Connection) -> None:
    tid = _active(conn)
    snap = Snapshot(conn)

    def msgs(day: date) -> list[summary.Message]:
        now = datetime(day.year, day.month, day.day, 8, tzinfo=WAW)
        return [m for m in summary.due(snap, now) if m.kind == f"promo_track_{tid}"]

    assert msgs(date(2026, 11, 13)) == []  # 6 dni
    (five,) = msgs(date(2026, 11, 14))
    assert "Aplikacja" in five.text and five.period == "2026-11-19-5"
    summary.mark_sent(conn, five)
    assert msgs(date(2026, 11, 14)) == []
    assert len(msgs(date(2026, 11, 18))) == 1  # 1 dzień
    promo_track.toggle_condition(conn, conn.execute("SELECT id FROM promo_condition").fetchone()[0])
    assert msgs(date(2026, 11, 18)) == []  # spełnione: bez pusha


def test_start_rejects_duplicate_archived_and_unconfirmed(conn: sqlite3.Connection) -> None:
    oid = offer(conn)
    promo_track.start(conn, oid, TODAY)
    with pytest.raises(promo_track.PromoError):
        promo_track.start(conn, oid, TODAY)
    gone = offer(conn, "Bank Z")
    invest.archive_offer(conn, gone)
    with pytest.raises(promo_track.PromoError):
        promo_track.start(conn, gone, TODAY)


def test_paid_track_cannot_be_reopened(conn: sqlite3.Connection) -> None:
    tid = promo_track.start(conn, offer(conn, "Bank X"), TODAY)
    promo_track.mark_paid(conn, tid, "income", TODAY)
    with pytest.raises(promo_track.PromoError):
        promo_track.set_status(conn, tid, "failed")


def test_bad_amounts_raise_piggy_error_for_routes(conn: sqlite3.Connection) -> None:
    tid = promo_track.start(conn, offer(conn), TODAY)
    for bad in ("abc", "0", "-5"):
        with pytest.raises(PiggyError):
            promo_track.set_bonus(conn, tid, bad)


def test_income_ignores_internal_transfers(conn: sqlite3.Connection) -> None:
    tid = promo_track.start(conn, offer(conn), TODAY)
    promo_track.add_condition(conn, tid, "income", "Wpływy", "1000")
    add(conn, "1200.00", "transfer_in", day="2026-10-25", transfer_group="g1")
    assert promo_track.tracks(conn)[0].conditions[0].progress == D("0.00")


async def test_propose_out_of_range_values_do_not_raise(conn: sqlite3.Connection) -> None:
    tid = track_with_text(conn)
    fake = Fake({"bonus": 0.001, "conditions": [{"kind": "income", "label": "x", "target": 0.001}]})
    msg = await promo_track.propose(conn, AI, TODAY, tid, fake)
    assert msg and "ręcznie" in msg


def test_income_ignores_inflow_from_own_savings(conn: sqlite3.Connection) -> None:  # E10b (g)
    conn.execute(
        "INSERT INTO savings_account (name, account_number, opening_date, created_at) "
        "VALUES ('Konto X', '00123456789012345678901234', '2026-01-01', '2026-01-01T00:00:00')"
    )
    tid = promo_track.start(conn, offer(conn), TODAY)
    promo_track.add_condition(conn, tid, "income", "Wpływy", "1000")
    add(
        conn,
        "1200.00",
        "transfer_in",
        day="2026-10-25",
        counterparty_account="PL00123456789012345678901234",
    )
    add(conn, "300.00", "transfer_in", day="2026-10-26")
    assert promo_track.tracks(conn)[0].conditions[0].progress == D("300.00")


def _edition(c: sqlite3.Connection, bank: str, start: str, end: str, status: str = "active") -> int:
    tid = promo_track.start_edition(
        c, bank, "Edycja", date.fromisoformat(start), date.fromisoformat(end), 5
    )
    c.execute("UPDATE promo_track SET status = ? WHERE id = ?", (status, tid))
    return tid


def test_active_for_bank_matches_case_insensitive_and_picks_latest_end(
    conn: sqlite3.Connection,
) -> None:
    _edition(conn, "Bank Millennium", "2026-10-01", "2026-11-30")
    late = _edition(conn, "Bank Millennium", "2026-10-10", "2027-01-31")
    assert promo_track.active_for_bank(conn, "MILLEN", TODAY).id == late  # type: ignore[union-attr]
    assert promo_track.active_for_bank(conn, "velo", TODAY) is None


def test_active_for_bank_skips_inactive_and_out_of_range(conn: sqlite3.Connection) -> None:
    _edition(conn, "Bank Millennium", "2026-10-01", "2026-12-31", "done")
    _edition(conn, "Bank Millennium", "2026-10-25", "2027-01-31")  # jeszcze się nie zaczęła
    _edition(conn, "Bank Millennium", "2026-08-01", "2026-10-18")  # już się skończyła
    assert promo_track.active_for_bank(conn, "millennium", TODAY) is None
