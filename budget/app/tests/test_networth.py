"""Majątek netto (M26 E1): składniki, strony bilansu, wskaźniki, kurs NBP i powiązanie aktywa."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget import fx, invest, networth

from .test_categorize_engine import add, conn
from .test_loan import make as make_loan
from .test_piggy import make as make_piggy
from .test_piggy import move
from .test_savings import PARKING
from .test_savings import make as make_savings

__all__ = ["conn"]

DAY = date(2026, 10, 20)


def balance(c: sqlite3.Connection, account: int, kind: str, amount: str, cur: str = "PLN") -> None:
    c.execute(
        "INSERT INTO balance_snapshot (account_id, balance_type, amount, currency, fetched_at) "
        "VALUES (?, ?, ?, ?, '2026-10-20T06:00:00+00:00')",
        (account, kind, amount, cur),
    )


def eur_account(c: sqlite3.Connection) -> int:
    c.execute(
        "INSERT INTO account (id, kind, currency, display_name, created_at) "
        "VALUES (3, 'fx', 'EUR', 'Konto EUR', '2026-01-01')"
    )
    balance(c, 3, "ITAV", "100.00", "EUR")
    return 3


def by_group(nw: networth.NetWorth, group: str) -> list[networth.Component]:
    return [c for c in nw.components if c.group == group]


def test_accounts_card_and_eur(conn: sqlite3.Connection) -> None:
    balance(conn, 1, "ITAV", "1000.00")
    balance(conn, 2, "ITBD", "300.00")  # zadłużenie karty
    eur_account(conn)
    fx.store(conn, "EUR", {date(2026, 10, 19): Decimal("4.2500")})  # poniedziałek, dzień wcześniej
    nw = networth.compute(conn, DAY)
    assert [c.amount for c in by_group(nw, networth.ACCOUNTS)] == [Decimal(1000), Decimal(425)]
    eur = by_group(nw, networth.ACCOUNTS)[1]
    assert eur.note == "100.00 EUR po 4.2500" and not nw.missing_fx
    card = by_group(nw, networth.CARD)[0]
    assert card.liability and card.amount == Decimal(300)
    assert (nw.assets, nw.liabilities, nw.total) == (Decimal(1425), Decimal(300), Decimal(1125))


def test_eur_without_rate_is_zero_and_flagged(conn: sqlite3.Connection) -> None:
    eur_account(conn)
    nw = networth.compute(conn, DAY)
    assert nw.missing_fx and nw.assets == Decimal(0)
    fx.store(conn, "EUR", {date(2026, 9, 1): Decimal("4.30")})  # starsza niż LOOKBACK
    assert networth.compute(conn, DAY).missing_fx


def test_card_without_debt_and_negative_card_balance_are_skipped(conn: sqlite3.Connection) -> None:
    balance(conn, 2, "ITBD", "-50.00")  # nadpłata karty nie jest aktywem
    assert not by_group(networth.compute(conn, DAY), networth.CARD)


def test_savings_piggies_and_linked_asset_counted_once(conn: sqlite3.Connection) -> None:
    sid = make_savings(conn, name="Profit", opening_balance="1000", opening_date="2026-10-01")
    make_savings(
        conn,
        name="Parking",
        account_number=PARKING,
        opening_balance="500",
        parking_for=sid,
        opening_date="2026-10-01",
    )
    make_piggy(conn, opening_balance="200")
    twin = invest.save_asset(
        conn, None, "account", "Profit w Inwestycjach", "1000", "", "", "", False
    )
    invest.save_asset(conn, None, "bonds", "EDO", "5000", "", "", "", False)
    invest.link_savings(conn, twin, sid)
    nw = networth.compute(conn, DAY)
    assert sum(c.amount for c in by_group(nw, networth.SAVINGS)) == Decimal(1500)
    assert [c.amount for c in by_group(nw, networth.PIGGIES)] == [Decimal(200)]
    assert [c.name for c in by_group(nw, networth.INVESTMENTS)] == ["EDO"]
    assert nw.assets == Decimal(6700)


def test_stale_asset_values(conn: sqlite3.Connection) -> None:
    old = invest.save_asset(conn, None, "bonds", "Stare", "100", "", "", "", False)
    invest.save_asset(conn, None, "etf", "Świeże", "100", "", "", "", False)
    conn.execute("UPDATE invest_asset SET valued_at = '2026-07-01' WHERE id = ?", (old,))
    nw = networth.compute(conn, DAY)
    assert [c.name for c in nw.stale] == ["Stare"]
    assert by_group(nw, networth.INVESTMENTS)[0].note == "wartość z 01.07.2026"


def test_valued_at_moves_only_when_amount_changes(conn: sqlite3.Connection) -> None:
    aid = invest.save_asset(conn, None, "bonds", "EDO", "100", "", "", "", False)
    conn.execute("UPDATE invest_asset SET valued_at = '2026-01-01' WHERE id = ?", (aid,))
    invest.save_asset(conn, aid, "bonds", "EDO 2", "100", "", "", "", False)  # tylko nazwa
    assert invest.all_assets(conn)[0].valued_at == date(2026, 1, 1)
    invest.save_asset(conn, aid, "bonds", "EDO 2", "150", "", "", "", False)
    assert invest.all_assets(conn)[0].valued_at > date(2026, 1, 1)


def test_link_savings_validates(conn: sqlite3.Connection) -> None:
    aid = invest.save_asset(conn, None, "account", "Konto", "100", "", "", "", False)
    with pytest.raises(invest.InvestError, match="konta oszczędnościowego"):
        invest.link_savings(conn, aid, 99)
    with pytest.raises(invest.InvestError, match="aktywa"):
        invest.link_savings(conn, 99, None)
    sid = make_savings(conn)
    invest.link_savings(conn, aid, sid)
    assert invest.all_assets(conn)[0].savings_id == sid
    invest.link_savings(conn, aid, None)
    assert invest.all_assets(conn)[0].savings_id is None


def test_loans_are_liabilities_with_ltv_and_liquidity(conn: sqlite3.Connection) -> None:
    balance(conn, 1, "ITAV", "20000.00")
    make_loan(conn, principal="100000", principal_date="2026-10-20", last_payment_date="2046-10-20")
    nw = networth.compute(conn, DAY, spend=Decimal(4000))
    assert nw.liabilities == Decimal(100000) and nw.total == Decimal(-80000)
    assert nw.liquid == Decimal(20000) and nw.liquidity_months == Decimal("5.0")
    assert nw.ltv == Decimal("5.0000")
    assert networth.compute(conn, DAY).liquidity_months is None  # bez wydatków


def test_ratios_none_without_loan_or_assets() -> None:
    nw = networth.NetWorth(DAY, ())
    assert nw.ltv is None and nw.liquidity_months is None and nw.total == Decimal(0)


def test_rates_pick_table_on_or_before_day(conn: sqlite3.Connection) -> None:
    fx.store(conn, "EUR", {date(2026, 10, 16): Decimal("4.2"), date(2026, 10, 19): Decimal("4.3")})
    rates = fx.Rates(conn)
    assert rates.at("EUR", date(2026, 10, 19)) == (date(2026, 10, 19), Decimal("4.3"))
    assert rates.at("EUR", date(2026, 10, 18)) == (date(2026, 10, 16), Decimal("4.2"))
    assert rates.get("EUR", date(2026, 10, 19)) == Decimal("4.2")  # ściśle przed dniem
    assert rates.at("EUR", date(2026, 11, 20)) is None and rates.at("USD", DAY) is None


async def test_refresh_fetches_when_stale_and_never_raises(conn: sqlite3.Connection) -> None:
    eur_account(conn)
    calls: list[tuple[str, date, date]] = []

    async def fake(cur: str, start: date, end: date) -> dict[date, Decimal]:
        calls.append((cur, start, end))
        return {date(2026, 10, 19): Decimal("4.25")}

    await fx.refresh(conn, DAY, fake)
    assert calls == [("EUR", date(2026, 10, 10), DAY)]
    assert networth.compute(conn, DAY).assets == Decimal("425.00")
    await fx.refresh(conn, DAY, fake)  # świeży kurs — bez drugiego zapytania
    assert len(calls) == 1

    async def broken(cur: str, start: date, end: date) -> dict[date, Decimal]:
        raise RuntimeError("NBP leży")

    conn.execute("DELETE FROM fx_rate")
    await fx.refresh(conn, DAY, broken)  # nie rzuca


def test_nbp_parse_and_spans() -> None:
    body = {"rates": [{"effectiveDate": "2026-10-19", "mid": 4.2512}]}
    assert fx.parse(body) == {date(2026, 10, 19): Decimal("4.2512")}
    chunks = fx.spans(date(2026, 1, 1), date(2026, 6, 30))
    assert chunks[0] == (date(2026, 1, 1), date(2026, 4, 3))
    assert chunks[-1][1] == date(2026, 6, 30) and len(chunks) == 2


# --- E2: historia (odtwarzanie wstecz i migawki) ---------------------------------------------


def total_at(c: sqlite3.Connection, day: date) -> networth.NetWorth:
    return networth.reconstruct(c, day)


def test_reconstruct_account_and_card_walk_back_through_transactions(
    conn: sqlite3.Connection,
) -> None:
    balance(conn, 1, "ITAV", "1000.00")
    balance(conn, 2, "ITBD", "300.00")
    add(conn, "200", "transfer_in", "wpływ", "X", day="2026-10-10")
    add(conn, "-50", "card", "zakup", "Y", day="2026-09-20")
    add(conn, "-100", "card", "zakup karta", "Z", day="2026-09-10", account=2)
    add(conn, "-100", "card", "zakup karta", "Z", day="2026-10-05", account=2)
    sep30 = total_at(conn, date(2026, 9, 30))
    assert by_group(sep30, networth.ACCOUNTS)[0].amount == Decimal(800)
    assert by_group(sep30, networth.CARD)[0].amount == Decimal(200)
    sep1 = total_at(conn, date(2026, 9, 1))
    assert by_group(sep1, networth.ACCOUNTS)[0].amount == Decimal(850)
    assert not by_group(sep1, networth.CARD)  # przed pierwszą transakcją kartą
    assert networth.compute(conn, DAY).total == Decimal(700)  # dziś: tylko ostatnie migawki


def test_reconstruct_piggy_from_transfers_and_skips_future_sources(
    conn: sqlite3.Connection,
) -> None:
    make_piggy(conn, opening_balance="100")
    move(conn, "-50", "2026-09-20")
    assert by_group(total_at(conn, date(2026, 9, 30)), networth.PIGGIES)[0].amount == Decimal(150)
    assert by_group(total_at(conn, date(2026, 9, 10)), networth.PIGGIES)[0].amount == Decimal(100)
    make_savings(conn, opening_balance="1000", opening_date="2026-09-01")
    make_loan(conn, principal="5000", principal_date="2026-09-15", last_payment_date="2030-01-20")
    invest.save_asset(conn, None, "deposit", "Lokata", "700", None, "2026-09-25", None, False)
    aug = total_at(conn, date(2026, 8, 31))
    assert not by_group(aug, networth.SAVINGS) and not by_group(aug, networth.LOANS)
    sep20 = total_at(conn, date(2026, 9, 20))
    assert by_group(sep20, networth.SAVINGS) and by_group(sep20, networth.LOANS)
    assert not by_group(sep20, networth.INVESTMENTS)
    assert by_group(total_at(conn, date(2026, 9, 30)), networth.INVESTMENTS)


def test_backfill_month_ends_idempotent_and_keeps_exact_points(conn: sqlite3.Connection) -> None:
    balance(conn, 1, "ITAV", "1000.00")
    add(conn, "-50", "card", "zakup", "Y", day="2026-08-15")
    assert networth.first_day(conn) == date(2026, 8, 15)
    assert not networth.has_history(conn)
    assert networth.backfill(conn, DAY) == 2  # 31.08 i 30.09
    assert networth.has_history(conn)
    rows = conn.execute("SELECT day, approx FROM networth_snapshot ORDER BY day").fetchall()
    assert [(r["day"], r["approx"]) for r in rows] == [("2026-08-31", 1), ("2026-09-30", 1)]
    assert networth.backfill(conn, DAY) == 0  # niepusta tabela = bez ponownego odtwarzania
    networth.save(conn, networth.compute(conn, date(2026, 9, 30)))
    networth.save(conn, networth.reconstruct(conn, date(2026, 9, 30)), approx=True)
    row = conn.execute("SELECT * FROM networth_snapshot WHERE day = '2026-09-30'").fetchone()
    assert row["approx"] == 0 and Decimal(row["total"]) == Decimal(1000)
    assert '"group": "konta"' in row["components_json"]


def test_backfill_without_transactions_is_empty(conn: sqlite3.Connection) -> None:
    assert networth.first_day(conn) is None and networth.backfill(conn, DAY) == 0
