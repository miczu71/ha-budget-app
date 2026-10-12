"""Kalkulator scenariuszy kredytu (M9 E3a)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget import loan, loan_sim, savings
from budget.loan import Scenario

from .test_categorize_engine import conn
from .test_loan import make

__all__ = ["conn"]

TODAY = date(2026, 6, 25)  # po 5 ratach z 12 (20.02–20.06): 7 rat przed nami
ZERO = Decimal("0.00")
NO_SAVINGS = loan_sim.account_for(None)  # konto bez stóp: 0%


def lo_of(conn: sqlite3.Connection, **kw: object) -> loan.Loan:
    return loan.get(conn, make(conn, **kw))


def test_run_without_changes_matches_base_schedule(conn: sqlite3.Connection) -> None:
    lo = lo_of(conn)
    base = loan.schedule(lo)
    sim = loan_sim.simulate(lo, Scenario(), TODAY, NO_SAVINGS)
    assert sim is not None
    assert sim.base.rows == sim.scen.rows == [r for r in base if r.day > TODAY]
    assert sim.gain == 0 and sim.interest_saved == 0


@pytest.mark.parametrize("kind", ["equal", "decreasing"])
def test_lump_shorten_keeps_payment_and_ends_earlier(conn: sqlite3.Connection, kind: str) -> None:
    lo = lo_of(conn, installment_kind=kind)
    sim = loan_sim.simulate(lo, Scenario(lump=Decimal(20000)), TODAY, NO_SAVINGS)
    assert sim is not None
    first, then = sim.scen.rows[0], sim.base.rows[0]
    assert (
        (first.payment == then.payment) if kind == "equal" else (first.principal == then.principal)
    )
    assert sim.scen.payoff < sim.base.payoff and len(sim.scen.rows) < len(sim.base.rows)
    assert sim.interest_saved > 0 and sim.scen.rows[-1].balance == 0


@pytest.mark.parametrize("kind", ["equal", "decreasing"])
def test_lump_lower_keeps_term_and_cuts_payment(conn: sqlite3.Connection, kind: str) -> None:
    lo = lo_of(conn, installment_kind=kind)
    scen = Scenario(lump=Decimal(20000), variant="lower")
    sim = loan_sim.simulate(lo, scen, TODAY, NO_SAVINGS)
    assert sim is not None and sim.scen.payoff == sim.base.payoff
    assert sim.scen.installment < sim.base.installment and sim.interest_saved > 0
    shorter = loan_sim.simulate(lo, Scenario(lump=Decimal(20000)), TODAY, NO_SAVINGS)
    assert shorter is not None and shorter.interest_saved >= sim.interest_saved


def test_monthly_extra_shortens_and_closes(conn: sqlite3.Connection) -> None:
    lo = lo_of(conn)
    sim = loan_sim.simulate(lo, Scenario(monthly=Decimal(5000)), TODAY, NO_SAVINGS)
    assert sim is not None and sim.scen.payoff < sim.base.payoff
    assert sim.scen.rows[-1].balance == 0 and all(r.extra <= 5000 for r in sim.scen.rows)


def test_wibor_up_raises_equal_installment_and_interest(conn: sqlite3.Connection) -> None:
    lo = lo_of(conn)
    plain = loan_sim.simulate(lo, Scenario(), TODAY, NO_SAVINGS)
    up = loan_sim.simulate(lo, Scenario(wibor_delta=Decimal(1)), TODAY, NO_SAVINGS)
    assert plain is not None and up is not None
    assert up.base.installment > plain.base.installment and up.base.interest > plain.base.interest
    assert up.loan_rate == Decimal("7.00")
    # zmiana od przyszłej daty nie rusza najbliższej raty
    later = Scenario(wibor_delta=Decimal(1), wibor_from=date(2026, 9, 1))
    late = loan_sim.simulate(lo, later, TODAY, NO_SAVINGS)
    assert late is not None and late.base.rows[0] == plain.base.rows[0]
    assert late.base.rows[-1].payment != plain.base.rows[-1].payment


def test_margin_change_applies_from_date(conn: sqlite3.Connection) -> None:
    lo = lo_of(conn)
    scen = Scenario(margin=Decimal(1), margin_from=date(2026, 8, 1))
    sim = loan_sim.simulate(lo, scen, TODAY, NO_SAVINGS)
    plain = loan_sim.simulate(lo, Scenario(), TODAY, NO_SAVINGS)
    assert sim is not None and plain is not None
    assert sim.base.rows[0] == plain.base.rows[0] and sim.base.interest < plain.base.interest


def test_gain_is_interest_saved_in_horizon_when_savings_pay_nothing(
    conn: sqlite3.Connection,
) -> None:
    lo = lo_of(conn)
    sim = loan_sim.simulate(lo, Scenario(lump=Decimal(20000)), TODAY, NO_SAVINGS, months=4)
    assert sim is not None
    inside = [r for r in sim.base.rows if r.day <= sim.horizon_end]
    saved = sum(r.interest for r in inside) - sum(
        r.interest for r in sim.scen.rows if r.day <= sim.horizon_end
    )
    assert sim.gain == saved and sim.gain > 0


def test_verdict_flips_with_savings_rate(conn: sqlite3.Connection) -> None:
    lo = lo_of(conn, last_payment_date="2036-01-20")  # długi kredyt, 6% rocznie
    scen = Scenario(lump=Decimal(50000))
    low = loan_sim.simulate(lo, scen, TODAY, loan_sim.account_for(None, Decimal(3)), months=60)
    high = loan_sim.simulate(lo, scen, TODAY, loan_sim.account_for(None, Decimal(9)), months=60)
    assert low is not None and high is not None
    assert low.gain > 0 > high.gain
    assert low.savings_net == Decimal(3) * Decimal("0.81")


def test_always_promo_extends_promo_rate_past_its_end() -> None:
    real = savings.Account(
        1,
        "Profit",
        "0" * 26,
        ZERO,
        date(2026, 1, 1),
        Decimal("0.5"),
        Decimal("5.25"),
        Decimal(200000),
        date(2026, 9, 1),
    )
    off = loan_sim.account_for(real)
    on = loan_sim.account_for(real, always_promo=True)
    assert savings.daily(off, Decimal(10000), date(2026, 12, 1)) < savings.daily(
        on, Decimal(10000), date(2026, 12, 1)
    )
    assert loan_sim.account_for(real, Decimal(4), True).promo_rate is None  # wpisana stopa wygrywa


def test_variants_table_rows_and_ordering(conn: sqlite3.Connection) -> None:
    lo = lo_of(conn)
    table = loan_sim.variants(lo, Scenario(lump=Decimal(20000)), TODAY)
    assert [d for d, *_ in table] == [Decimal(k) for k in range(-2, 3)]
    for _, plain, shorten, lower in table:
        assert shorten.payoff < plain.payoff and lower.installment < plain.installment
    assert table[4][1].interest > table[0][1].interest  # wyższy WIBOR = więcej odsetek


def test_variants_step_scales_deltas(conn: sqlite3.Connection) -> None:
    table = loan_sim.variants(lo_of(conn), Scenario(), TODAY, Decimal("0.25"))
    assert [d for d, *_ in table] == [Decimal(k) / 4 for k in range(-2, 3)]


def test_paid_off_loan_has_no_simulation(conn: sqlite3.Connection) -> None:
    assert loan_sim.simulate(lo_of(conn), Scenario(), date(2027, 6, 1), NO_SAVINGS) is None
