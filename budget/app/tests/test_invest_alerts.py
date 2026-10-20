"""Agent inwestycyjny (M22 E4): dzwonek, push po wypłacie, uzasadnienie od modelu, źródło czatu."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from budget import inbox, invest, invest_why, summary
from budget.ask import sources
from budget.settings import Settings
from budget.snapshot import Snapshot
from budget.storage import db
from budget.suggest.client import AIError

from .test_categorize_engine import conn
from .test_invest import inputs
from .test_savings import make as make_savings

__all__ = ["conn"]

D = Decimal
TODAY = date(2026, 10, 19)
NOW = datetime(2026, 10, 19, 8, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
S = invest.Settings()


def ctx() -> inbox.Context:
    return inbox.Context(NOW, None, None)  # type: ignore[arg-type]  # dostawcy czytają tylko `now`


def confirmed(conn: sqlite3.Connection, bank: str, rate: str, kind: str = "account") -> int:
    oid = invest.save_offer(
        conn, kind, bank, rate, "", "", "12" if kind == "deposit" else "", "", False
    )
    conn.execute("UPDATE invest_offer SET status = 'confirmed' WHERE id = ?", (oid,))
    return oid


def own_account(conn: sqlite3.Connection, rate: str = "2") -> None:
    make_savings(conn, opening_balance="10000", opening_date="2026-01-01", base_rate=rate)


# --- lepsza oferta ---


def test_better_offer_beats_current_account_by_threshold(conn: sqlite3.Connection) -> None:
    own_account(conn, "2")
    confirmed(conn, "Bank A", "6")  # ≈ +4 pp · 0,81 · 10 000 zł ≈ 320 zł rocznie
    (b,) = invest.better_offers(conn, TODAY, S)
    assert b.offer.bank == "Bank A" and 280 <= b.gain <= 340
    (item,) = inbox.invest_better_offer(conn, ctx(), None)  # type: ignore[arg-type]
    assert item.kind == "invest_better_offer" and item.title == "Lepsza oferta: Bank A 6%"
    assert item.link == "/invest#offers"


def test_better_offer_below_threshold_or_unconfirmed_or_hidden_is_silent(
    conn: sqlite3.Connection,
) -> None:
    own_account(conn, "2")
    confirmed(conn, "Bank A", "2.5")  # zysk ≈ 40 zł < 200
    oid = invest.save_offer(conn, "account", "Bank B", "9", "", "", "", "", False)
    conn.execute("UPDATE invest_offer SET status = 'review' WHERE id = ?", (oid,))
    assert invest.better_offers(conn, TODAY, S) == []
    conn.execute(
        "UPDATE invest_offer SET status = 'confirmed', new_clients_only = 1 WHERE id = ?", (oid,)
    )
    invest.save_bank(conn, "Bank B")  # klient banku: oferta „tylko dla nowych” znika
    assert invest.better_offers(conn, TODAY, S) == []


def test_better_offer_threshold_comes_from_settings(conn: sqlite3.Connection) -> None:
    own_account(conn, "2")
    confirmed(conn, "Bank A", "6")
    invest.save_settings(conn, "3", "0;6;9", "0.2", "3", "500")
    assert invest.load_settings(conn).better_offer == D(500)
    assert inbox.invest_better_offer(conn, ctx(), None) == []  # type: ignore[arg-type]
    with pytest.raises(invest.InvestError):
        invest.save_settings(conn, "3", "0;6;9", "0.2", "3", "abc")


def test_better_offer_also_checks_account_assets(conn: sqlite3.Connection) -> None:
    invest.save_asset(conn, None, "account", "Moje konto", "20000", "1", "", "", False)
    confirmed(conn, "Bank A", "5")
    (b,) = invest.better_offers(conn, TODAY, S)
    assert b.holder == "Moje konto" and 500 < b.gain < 700  # 20 000 · 4 pp · 0,81 ≈ 648


# --- termin lokaty / wykup obligacji ---


def test_maturity_within_two_weeks(conn: sqlite3.Connection) -> None:
    invest.save_asset(conn, None, "deposit", "Lokata X", "5000", "5", "", "2026-10-30", False)
    invest.save_asset(conn, None, "bonds", "EDO Y", "3000", "", "", "2026-12-01", False)
    invest.save_asset(conn, None, "deposit", "Stara", "1000", "5", "", "2026-10-01", False)
    (item,) = inbox.invest_maturity(conn, ctx(), None)  # type: ignore[arg-type]
    assert item.title == "Lokata X: termin 30.10" and item.severity == "warn"
    assert "za 11 dni" in item.detail
    assert [a.name for a in invest.maturities(conn, TODAY)] == ["Lokata X"]


# --- push po wypłacie ---


def advice(**kw: Any) -> invest.Advice:
    inp = inputs(**{"surplus": D(1500), **kw})
    s = invest.Settings()
    deposit = invest.Option("account_own", "Konto A", D(400), D(400), D(1))
    rec = invest.recommend(inp, s, [deposit])
    return invest.Advice(s, inp, invest.buckets(inp, s), [deposit], rec, D(18000), TODAY)


def test_invest_message_lists_parts_and_why() -> None:
    msg = summary.invest_message(advice(), "Poduszka najpierw.")
    assert msg is not None and msg.kind == "invest_monthly" and msg.period == "2026-10-19"
    assert f"Odłóż {summary.zl(D(1500))}" in msg.text and "→ Konto A (poduszka)" in msg.text
    assert msg.text.endswith("Poduszka najpierw.")


def test_invest_message_deficit_and_no_data() -> None:
    msg = summary.invest_message(advice(surplus=D(-300)))
    assert msg is not None and msg.text.startswith("Nadwyżki brak")
    assert summary.invest_message(advice(surplus=None)) is None


def test_due_sends_invest_message_once_per_payday(conn: sqlite3.Connection) -> None:
    snap = Snapshot(conn)
    now = datetime(2026, 10, 19, 8, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
    got = lambda: summary.invest_message(advice())  # noqa: E731
    (msg,) = [m for m in summary.due(snap, now, got) if m.kind == "invest_monthly"]
    summary.mark_sent(conn, msg)
    assert "invest_monthly" not in [m.kind for m in summary.due(snap, now, got)]
    assert "invest_monthly" not in [m.kind for m in summary.due(snap, now, lambda: None)]


# --- uzasadnienie od modelu ---


class Fake:
    def __init__(self, *answers: dict[str, Any] | Exception) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    async def __call__(self, **kw: Any) -> tuple[dict[str, Any], int]:
        self.prompts.append(kw["prompt"])
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a, 50


AI = Settings(ai_base_url="http://router:3003/v1", ai_api_key="k", invest_daily_calls=2)


def test_why_input_has_amounts_but_no_names() -> None:
    data = invest_why.facts(advice())
    assert data is not None
    assert "Konto A" not in str(data) and "własne konto oszczędnościowe" in str(data)
    assert invest_why.facts(advice(surplus=D(-5))) is None


async def test_why_is_stored_matches_fingerprint_and_is_not_repeated(
    conn: sqlite3.Connection,
) -> None:
    adv, fake = advice(), Fake({"text": "Najpierw poduszka. Potem długi termin."})
    await invest_why.refresh(conn, AI, adv, NOW, fake)
    assert invest_why.text(conn, adv) == "Najpierw poduszka. Potem długi termin."
    await invest_why.refresh(conn, AI, adv, NOW, fake)  # bez zmian = bez drugiego wywołania
    assert len(fake.prompts) == 1 and "Konto A" not in fake.prompts[0]
    assert invest_why.text(conn, advice(surplus=D(900))) is None  # inna rekomendacja = brak tekstu


async def test_why_survives_model_errors_and_respects_limit(conn: sqlite3.Connection) -> None:
    await invest_why.refresh(conn, AI, advice(), NOW, Fake(AIError("limit")))
    assert db.kv_get(conn, invest_why.KEY) is None
    off = Settings(ai_base_url="http://r/v1", ai_api_key="k", invest_daily_calls=0)
    fake = Fake()
    await invest_why.refresh(conn, off, advice(), NOW, fake)
    assert fake.prompts == []


# --- źródło czatu ---


def test_chat_source_is_registered_and_redacts_names(conn: sqlite3.Connection) -> None:
    assert "invest" in sources.NAMES
    c = sources.Ctx(conn, Snapshot(conn), TODAY, NOW, date(2026, 10, 1))
    res = sources.run("invest", c)
    assert res.link == "/invest" and res.note  # pusta księga: brak prognozy


# --- poprawki z code-review (E4) ---


def test_confirm_with_bad_limit_is_an_invest_error_not_a_crash(conn: sqlite3.Connection) -> None:
    oid = invest.save_offer(conn, "account", "Bank A", "5", "", "", "", "", False)
    with pytest.raises(invest.InvestError):
        invest.confirm_offer(conn, oid, "Bank A", {"rate": "5", "limit_amount": "abc"})


# --- vesting akcji (M11 E3) ---


def hold(conn: sqlite3.Connection, vest: str | None, qty: str | None = "100") -> None:
    db.kv_set(
        conn,
        "stocks_nokia",
        {
            "market_value": "1000",
            "unvested_qty": "500",
            "price": "20.5",
            "next_vest": vest,
            "next_vest_qty": qty,
            "fetched_at": NOW.isoformat(),
        },
    )


def test_vest_soon_within_two_weeks(conn: sqlite3.Connection) -> None:
    hold(conn, "2026-10-30")
    (item,) = inbox.vest_soon(conn, ctx(), None)  # type: ignore[arg-type]
    assert item.title == "Vesting akcji 30.10" and item.link == "/networth"
    assert (
        "Za 11 dni" in item.detail
        and "100 akcji" in item.detail
        and summary.zl(D("2050")) in item.detail
    )


@pytest.mark.parametrize("vest", ["2026-11-10", "2026-10-18", None])
def test_vest_soon_silent_when_far_past_or_unknown(
    conn: sqlite3.Connection, vest: str | None
) -> None:
    hold(conn, vest)
    assert inbox.vest_soon(conn, ctx(), None) == []  # type: ignore[arg-type]


def test_vest_soon_silent_without_holding(conn: sqlite3.Connection) -> None:
    assert inbox.vest_soon(conn, ctx(), None) == []  # type: ignore[arg-type]
