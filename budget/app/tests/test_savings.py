"""Konto oszczędnościowe poza Enable Banking (M10 E2)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget import piggy, savings
from budget.snapshot import Snapshot

from .test_categorize_engine import add, conn
from .test_piggy import DIGITS, NUMBER, move

__all__ = ["conn"]


def make(c: sqlite3.Connection, **kw: object) -> int:
    args: dict[str, object] = {
        "account_id": None,
        "name": "Oszczędnościowe",
        "account_number": NUMBER,
        "opening_balance": "1000",
        "opening_date": "2026-09-01",
    }
    args.update(kw)
    return savings.save(c, **args)  # type: ignore[arg-type]


def test_save_validates(conn: sqlite3.Connection) -> None:
    with pytest.raises(savings.SavingsError, match="datę"):
        make(conn, opening_date="")
    with pytest.raises(piggy.PiggyError, match="26 cyfr"):
        make(conn, account_number="123")
    aid = make(conn)
    acc = savings.get(conn, aid)
    assert acc.account_number == DIGITS and acc.masked == "PL** **** … 7777"
    with pytest.raises(savings.SavingsError, match="już jest"):
        make(conn, name="Inne")
    make(conn, account_id=aid, account_number="", opening_balance="1500")  # numer bez zmiany
    assert savings.get(conn, aid).account_number == DIGITS
    assert savings.get(conn, aid).opening_balance == Decimal(1500)


def test_balance_from_opening_and_transfers(conn: sqlite3.Connection) -> None:
    acc = savings.get(conn, make(conn))
    move(conn, "-200", "2026-08-20")  # przed datą salda — już w nim
    move(conn, "-300", "2026-09-10")  # wpłata
    move(conn, "100", "2026-09-20")  # wypłata
    assert savings.estimate(conn, acc, date(2026, 9, 30)).total == Decimal(1200)  # bez stóp


def test_transfers_are_outside_flex_pool(conn: sqlite3.Connection) -> None:
    make(conn)
    tid = move(conn, "-300", "2026-09-10")
    other = add(conn, "-20", "card", "kawa", "KAWIARNIA", day="2026-09-11")
    ids = Snapshot(conn).piggy_ids()
    assert tid in ids and other not in ids
    assert savings.txn_ids(conn) == {tid}


def test_archive_hides_account(conn: sqlite3.Connection) -> None:
    aid = make(conn)
    savings.archive(conn, aid)
    assert savings.all_accounts(conn) == []
    with pytest.raises(savings.SavingsError):
        savings.archive(conn, 999)
    assert date(2026, 9, 1) == savings.get(conn, aid).opening_date


def rated(c: sqlite3.Connection, **kw: object) -> savings.Account:
    return savings.get(c, make(c, opening_balance="10000", opening_date="2026-01-01", **kw))


def test_interest_base_rate_capitalizes_monthly_net_of_tax(conn: sqlite3.Connection) -> None:
    acc = rated(conn, base_rate="3.65")  # 0,01% dziennie
    est = savings.estimate(conn, acc, date(2026, 1, 31))  # 30 dni od 2026-01-01
    assert est.earned == Decimal("24.30") and est.accrued == Decimal(0)  # 30 zł × 0,81
    assert est.balance == Decimal("10024.30")
    feb = savings.estimate(conn, acc, date(2026, 2, 10))
    assert feb.accrued > 0 and feb.total == feb.balance + feb.accrued
    assert feb.accrued == Decimal("8.12")  # 10 dni od salda 10024,30 × 0,01% × 0,81


def test_promo_limit_and_end_date(conn: sqlite3.Connection) -> None:
    acc = rated(
        conn, base_rate="0", promo_rate="3.65", promo_limit="5000", promo_until="2026-01-10"
    )
    est = savings.estimate(conn, acc, date(2026, 1, 31))
    assert est.earned == Decimal("3.65")  # 9 dni × 0,50 zł × 0,81, po 10.01 stopa bazowa 0


def test_transfers_change_interest_base(conn: sqlite3.Connection) -> None:
    acc = rated(conn, base_rate="3.65")
    move(conn, "-10000", "2026-01-16")  # wpłata podwaja saldo od 16.01
    est = savings.estimate(conn, acc, date(2026, 1, 31))
    assert est.earned == Decimal("37.26")  # (14 dni × 1 zł + 16 dni × 2 zł) × 0,81


def test_rate_validation(conn: sqlite3.Connection) -> None:
    with pytest.raises(savings.SavingsError, match="stopę bazową"):
        make(conn, base_rate="150")
    with pytest.raises(savings.SavingsError, match="datę końca"):
        make(conn, promo_rate="5")
    aid = make(conn, promo_rate="5", promo_until="2026-12-31", promo_limit="2000", base_rate="2")
    acc = savings.get(conn, aid)
    assert (acc.promo_rate, acc.promo_limit, acc.base_rate) == (5, 2000, 2)
    assert acc.promo_until == date(2026, 12, 31)


def test_promo_bell_and_push(conn: sqlite3.Connection) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from budget import inbox, summary

    make(conn, base_rate="2", promo_rate="5", promo_until="2026-10-20")
    snap = Snapshot(conn)
    waw = ZoneInfo("Europe/Warsaw")

    def kinds(day: int, hour: int = 8) -> list[str]:
        return [m.kind for m in summary.due(snap, datetime(2026, 10, day, hour, 0, tzinfo=waw))]

    assert "savings_promo_1" in kinds(6)  # 14 dni przed
    assert "savings_promo_1" in kinds(17)  # 3 dni przed
    assert "savings_promo_1" not in kinds(10)
    bell = [
        i
        for i in inbox.items(snap, datetime(2026, 10, 10, 9, tzinfo=waw), inbox.BalanceMemo())
        if i.kind == "savings_promo"
    ]
    assert len(bell) == 1 and "kończy się za 10 dni" in bell[0].title
    assert bell[0].link == "/piggy#savings" and "potem 2" in bell[0].detail
    later = datetime(2026, 10, 21, 9, tzinfo=waw)
    assert not [
        i for i in inbox.items(snap, later, inbox.BalanceMemo()) if i.kind == "savings_promo"
    ]


def test_monthly_rates_use_transfers_and_income(conn: sqlite3.Connection) -> None:
    make(conn)
    add(conn, "5000", "transfer_in", "wypłata", "PRACODAWCA", day="2026-09-05")
    move(conn, "-1000", "2026-09-10")  # wpłata
    move(conn, "250", "2026-09-20")  # wypłata
    rates = savings.monthly_rates(conn, date(2026, 10, 12))
    sep = next(m for m in rates if m.month == date(2026, 9, 1))
    assert (sep.saved, sep.income) == (Decimal(750), Decimal(5000))
    assert sep.rate == Decimal("0.15") and sep.frac == 0.15
    assert rates[-1].month == date(2026, 10, 1) and rates[-1].rate is None  # brak wpływów
    assert rates[-1].frac == 0.0 and len(rates) == 12


def test_overview_none_without_accounts(conn: sqlite3.Connection) -> None:
    assert savings.overview(conn, date(2026, 10, 12)) is None
    make(conn)
    ov = savings.overview(conn, date(2026, 10, 12))
    assert ov is not None and ov.total == Decimal(1000) and ov.current.month == date(2026, 10, 1)


def test_month_details_are_split_per_account(conn: sqlite3.Connection) -> None:
    other = "22 3333 4444 5555 6666 7777 8888"
    make(conn, name="Profit")
    make(conn, name="Cel roczny", account_number=other)
    move(conn, "-1000", "2026-09-10")  # Profit: wpłata
    move(conn, "250", "2026-09-20")  # Profit: wypłata
    move(conn, "-300", "2026-09-05", number="PL22333344445555666677778888")  # Cel roczny
    sep = next(m for m in savings.monthly_rates(conn, date(2026, 10, 12)) if m.month.month == 9)
    assert sep.saved == Decimal(1050)
    names = [
        (name, net, [(m.day.day, m.amount) for m in rows]) for name, net, rows in sep.by_account
    ]
    assert names == [
        ("Cel roczny", Decimal(300), [(5, Decimal(300))]),
        ("Profit", Decimal(750), [(10, Decimal(1000)), (20, Decimal(-250))]),
    ]


def test_activate_promo_sets_rates_and_ends_after_91_days(conn: sqlite3.Connection) -> None:
    aid = make(conn, opening_balance="0")
    savings.activate_promo(
        conn, aid, base_rate="0,5", promo_rate="5,25", new_funds="50 000", start="2026-10-20"
    )
    acc = savings.get(conn, aid)
    assert (acc.base_rate, acc.promo_rate, acc.promo_limit) == (
        Decimal("0.5"),
        Decimal("5.25"),
        50000,
    )
    assert acc.promo_until == date(2027, 1, 18)  # 91 dni łącznie z dniem przystąpienia
    assert acc.account_number == DIGITS and acc.opening_balance == 0  # reszta konta bez zmian


def test_activate_promo_validates(conn: sqlite3.Connection) -> None:
    aid = make(conn)
    ok = {"base_rate": "0,5", "promo_rate": "5,25", "new_funds": "1000", "start": "2026-10-20"}
    for bad, msg in (
        ({"new_funds": "250000"}, "do 200 000"),
        ({"new_funds": ""}, "podaj kwotę"),
        ({"promo_rate": ""}, "łączną stawkę"),
        ({"start": "jutro"}, "datę przystąpienia"),
    ):
        with pytest.raises(savings.SavingsError, match=msg):
            savings.activate_promo(conn, aid, **{**ok, **bad})  # type: ignore[arg-type]
    with pytest.raises(savings.SavingsError, match="Nie ma takiego"):
        savings.activate_promo(conn, 999, **ok)  # type: ignore[arg-type]


PARKING = "33 4444 5555 6666 7777 8888 9999"  # fikcyjny
PARKING_PL = "PL33444455556666777788889999"


def parking(conn: sqlite3.Connection) -> tuple[int, int]:
    profit = make(conn, name="Profit")
    return profit, make(conn, name="Parking", account_number=PARKING, parking_for=profit)


def test_parking_validates(conn: sqlite3.Connection) -> None:
    profit, park = parking(conn)
    assert savings.get(conn, park).parking_for == profit
    assert savings.get(conn, profit).parking_for is None
    with pytest.raises(savings.SavingsError, match="siebie"):
        make(conn, account_id=park, name="Parking", account_number="", parking_for=park)
    with pytest.raises(savings.SavingsError, match="Nie ma"):
        make(conn, name="Inne", account_number="44 1111 2222 3333 4444 5555 6666", parking_for=99)
    with pytest.raises(savings.SavingsError, match="parkingiem"):
        make(
            conn,
            name="Trzecie",
            account_number="44 1111 2222 3333 4444 5555 6666",
            parking_for=park,
        )


def test_parking_pairs_withdrawal_and_deposit_across_months(conn: sqlite3.Connection) -> None:
    add(conn, "5000", "transfer_in", "wypłata", "PRACODAWCA", day="2026-09-05")
    parking(conn)
    move(conn, "5000", "2026-09-30")  # wypłata z Profit
    move(conn, "-5000", "2026-10-02", number=PARKING_PL)  # wpłata na parking
    rates = {m.month: m for m in savings.monthly_rates(conn, date(2026, 10, 12))}
    sep, octo = rates[date(2026, 9, 1)], rates[date(2026, 10, 1)]
    assert (sep.saved, octo.saved) == (Decimal(0), Decimal(0))
    assert all(mv.transfer for mv in (*sep.moves, *octo.moves))
    assert savings.overview(conn, date(2026, 10, 12)).total == Decimal(2000)  # type: ignore[union-attr]


def test_parking_does_not_pair_distant_or_different_amounts(conn: sqlite3.Connection) -> None:
    parking(conn)
    move(conn, "5000", "2026-09-01")
    move(conn, "-5000", "2026-09-20", number=PARKING_PL)  # za późno (>7 dni)
    move(conn, "3000", "2026-09-22")
    move(conn, "-2500", "2026-09-23", number=PARKING_PL)  # inna kwota
    sep = next(m for m in savings.monthly_rates(conn, date(2026, 10, 12)) if m.month.month == 9)
    assert not any(mv.transfer for mv in sep.moves)
    assert sep.saved == Decimal(-500)


def test_transfer_between_savings_accounts_pairs_without_parking(
    conn: sqlite3.Connection,
) -> None:
    make(conn, name="A")
    make(conn, name="B", account_number=PARKING)  # konto bez parking_for
    move(conn, "2000", "2026-09-10")  # wypłata z A
    move(conn, "-2000", "2026-09-12", number=PARKING_PL)  # wpłata na B
    sep = next(m for m in savings.monthly_rates(conn, date(2026, 10, 12)) if m.month.month == 9)
    assert sum(mv.transfer for mv in sep.moves) == 2 and sep.saved == Decimal(0)


def test_movements_far_apart_or_different_amounts_between_accounts_count(
    conn: sqlite3.Connection,
) -> None:
    make(conn, name="A")
    make(conn, name="B", account_number=PARKING)
    move(conn, "5000", "2026-09-01")  # wypłata z A
    move(conn, "-5000", "2026-09-20", number=PARKING_PL)  # wpłata na B po >7 dniach
    move(conn, "3000", "2026-09-22")  # wypłata z A
    move(conn, "-2500", "2026-09-23", number=PARKING_PL)  # wpłata na B, inna kwota (>1 zł)
    sep = next(m for m in savings.monthly_rates(conn, date(2026, 10, 12)) if m.month.month == 9)
    assert not any(mv.transfer for mv in sep.moves)
    assert sep.saved == Decimal(-500)


def test_parking_pairs_each_movement_once(conn: sqlite3.Connection) -> None:
    parking(conn)
    move(conn, "1000", "2026-09-10")
    move(conn, "1000", "2026-09-11")
    move(conn, "-1000", "2026-09-12", number=PARKING_PL)
    sep = next(m for m in savings.monthly_rates(conn, date(2026, 10, 12)) if m.month.month == 9)
    assert sum(mv.transfer for mv in sep.moves) == 2 and sep.saved == Decimal(-1000)


# --- konto powiązane z księgą po numerze (M32 E7) ---------------------------------------------


def bank_account(
    c: sqlite3.Connection, iban: str | None, amount: str | None, kind: str = "ITAV"
) -> int:
    cur = c.execute(
        "INSERT INTO account (kind, iban, currency, bank, created_at) "
        "VALUES ('savings', ?, 'PLN', 'Bank A', '2026-01-01')",
        (iban,),
    )
    aid = int(cur.lastrowid or 0)
    if amount is not None:
        c.execute(
            "INSERT INTO balance_snapshot (account_id, balance_type, amount, currency, "
            "fetched_at) VALUES (?, ?, ?, 'PLN', '2026-10-20T06:00:00+00:00')",
            (aid, kind, amount),
        )
    return aid


def test_linked_account_uses_api_balance_and_pending_interest(conn: sqlite3.Connection) -> None:
    acc = savings.get(conn, make(conn, base_rate="3", opening_balance="1"))
    move(conn, "-300", "2026-10-05")  # przelew po dacie salda — ignorowany przy powiązaniu
    aid = bank_account(conn, "PL" + DIGITS, "10000.00")
    assert savings.linked_ledger_id(conn, acc) == aid
    est = savings.estimate(conn, acc, date(2026, 10, 20))
    assert est.total == est.balance == Decimal("10000.00") and est.accrued == 0
    assert est.pending > 0 and est.interest == 0
    assert est.as_of == date(2026, 10, 20)
    gross = sum(
        (savings.daily(acc, Decimal(10000), date(2026, 10, d)) for d in range(1, 21)), Decimal(0)
    )
    assert est.pending == savings.net(gross)


def test_link_matches_iban_without_prefix_and_falls_back_to_itbd(conn: sqlite3.Connection) -> None:
    acc = savings.get(conn, make(conn))
    bank_account(conn, DIGITS, "700.00", kind="ITBD")
    est = savings.estimate(conn, acc, date(2026, 10, 20))
    assert est.total == Decimal("700.00") and est.as_of is not None


def test_unlinked_or_without_snapshot_keeps_manual_path(conn: sqlite3.Connection) -> None:
    acc = savings.get(conn, make(conn))
    move(conn, "-300", "2026-09-10")
    manual = savings.estimate(conn, acc, date(2026, 9, 30))
    assert manual.total == Decimal(1300) and manual.as_of is None and manual.pending == 0
    bank_account(conn, "PL" + DIGITS, None)  # powiązane, ale bez migawki
    assert savings.estimate(conn, acc, date(2026, 9, 30)) == manual
    assert savings.linked_ledger_id(conn, acc) is not None
    other = bank_account(conn, "PL99999999999999999999999999", "5.00")
    assert other and savings.estimate(conn, acc, date(2026, 9, 30)) == manual
