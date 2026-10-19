"""Agent inwestycyjny (M22 E1, decyzja 30): koszyki, zysk netto opcji, rekomendacja, zapis."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget import invest, loan, loan_sim

from .test_categorize_engine import conn
from .test_loan import make

__all__ = ["conn"]

TODAY = date(2026, 6, 25)
D = Decimal
S = invest.Settings()  # 3 miesiące poduszki, ETF 0/6/9%, TER 0,2%, inflacja 3%


def offer(kind: str, rate: str, **kw: object) -> invest.Offer:
    args: dict[str, object] = {"id": 1, "kind": kind, "bank": "Bank A", "rate": D(rate)}
    args.update(kw)
    return invest.Offer(**args)  # type: ignore[arg-type]


def one(kind: str, rate: str, amount: str, years: str, **kw: object) -> invest.Option:
    (opt, *_) = invest.offer_options(offer(kind, rate, **kw), D(amount), D(years), S)
    return opt


# --- zysk netto: liczone ręcznie, ±1 zł ---


def test_deposit_one_year_is_rate_times_belka() -> None:
    opt = one("deposit", "5", "10000", "1", months=12)
    assert opt.net_gain == D("405.00") and opt.per_year == D("405.00")  # 10000 · 5% · 0,81


def test_deposit_rolls_over_with_capitalisation() -> None:
    opt = one("deposit", "5", "10000", "2", months=12)
    assert abs(opt.net_gain - D("826.40")) <= 1  # 10000 · (1,0405² − 1)


def test_deposit_term_longer_than_horizon_extends_the_horizon() -> None:
    opt = one("deposit", "5", "10000", "0.5", months=12)
    assert opt.net_gain == D("405.00") and opt.years == D(1)


def test_account_promo_limit_and_months() -> None:
    # 6% do 20 tys. przez 3 miesiące, reszta kwoty bez odsetek: 20000 · ((1 + 0,06·0,81/12)³ − 1)
    opt = one("account", "6", "30000", "1", limit_amount=D(20000), months=3)
    assert abs(opt.net_gain - D("243.99")) <= 1


def test_edo_ten_years_matches_hand_calculation() -> None:
    # 6% pierwszy rok, potem inflacja 3% + marża 1,5% = 4,5%; kapitalizacja roczna, Belka na końcu
    opt = one("edo", "6", "10000", "10", margin=D("1.5"))
    expected = (D("10000") * D("1.06") * D("1.045") ** 9 - 10000) * D("0.81")
    assert abs(opt.net_gain - expected) <= 1 and opt.liquid is False


def test_edo_early_redemption_fee_is_two_zloty_per_bond() -> None:
    full = one("edo", "6", "10000", "3", margin=D("1.5"))
    gross = D("10000") * D("1.06") * D("1.045") ** 2 - 10000
    assert abs(full.net_gain - (gross - 200) * D("0.81")) <= 1  # 100 obligacji · 2 zł


def test_coi_pays_interest_yearly_without_compounding() -> None:
    opt = one("coi", "6", "10000", "4", margin=D("1"))
    assert opt.net_gain == D("1458.00")  # (6% + 3 · 4%) · 10000 · 0,81


def test_tos_is_fixed_and_capitalised() -> None:
    opt = one("tos", "5", "10000", "3")
    assert abs(opt.net_gain - (D("10000") * D("1.05") ** 3 - 10000) * D("0.81")) <= 1


def test_edo_also_offered_inside_ike_without_belka() -> None:
    plain, ike = invest.offer_options(offer("edo", "6", margin=D("1.5")), D(10000), D(10), S)
    assert ike.label.endswith("IKE") and ike.net_gain > plain.net_gain
    assert abs(ike.net_gain - plain.net_gain / D("0.81")) <= 1


def test_etf_three_scenarios_net_of_ter_and_belka() -> None:
    opt = invest.etf_option(D(10000), D(5), S)
    assert opt.risky and opt.scenarios is not None and len(opt.scenarios) == 3
    mid = D(10000) * D("1.058") ** 5 - 10000
    assert abs(opt.net_gain - mid * D("0.81")) <= 1 and opt.net_gain == opt.scenarios[1]
    assert opt.scenarios[0] < 0  # 0% − TER: strata, bez podatku


def test_overpay_over_whole_loan_equals_interest_saved(conn: sqlite3.Connection) -> None:
    lo = loan.get(conn, make(conn))
    gain = loan_sim.overpay_gain(lo, D(20000), TODAY)
    sim = loan_sim.simulate(lo, loan.Scenario(lump=D(20000)), TODAY, loan_sim.account_for(None))
    assert sim is not None and gain == sim.interest_saved and gain > 0


def test_overpay_option_is_none_for_paid_off_loan(conn: sqlite3.Connection) -> None:
    lo = loan.get(conn, make(conn))
    assert invest.overpay_option(lo, D(20000), D(1), date(2030, 1, 1)) is None


# --- koszyki i rekomendacja ---


def inputs(**kw: object) -> invest.Inputs:
    args: dict[str, object] = {
        "spend": D(4000),
        "savings_total": D(5000),
        "free_above_buffer": D(2000),
        "goal_target": D(3000),
        "goal_have": D(1000),
        "assets_total": D(8000),
        "surplus": D(1500),
    }
    args.update(kw)
    return invest.Inputs(**args)  # type: ignore[arg-type]


def test_buckets_cushion_is_multiplier_times_spend() -> None:
    cushion, goals, long_term = invest.buckets(inputs(), S)
    assert (cushion.target, cushion.have, cushion.gap) == (D(12000), D(7000), D(5000))
    assert (goals.target, goals.have, goals.gap) == (D(3000), D(1000), D(2000))
    assert long_term.target is None and long_term.have == D(8000)


def test_negative_free_funds_do_not_reduce_cushion() -> None:
    cushion, *_ = invest.buckets(inputs(free_above_buffer=D(-900)), S)
    assert cushion.have == D(5000)


SAFE = [
    invest.Option("account", "Konto A", D(300), D(300), D(1), liquid=True),
    invest.Option("deposit", "Lokata B", D(500), D(500), D(1), liquid=False),
    invest.Option("edo", "EDO", D(600), D(600), D(10), liquid=False),
    invest.Option("etf", "ETF", D(900), D(900), D(5), liquid=True, risky=True),
]


def test_recommendation_fills_cushion_first_with_liquid_option() -> None:
    rec = invest.recommend(inputs(surplus=D(1500)), S, SAFE)
    assert rec.state == "invest"
    assert [(p.bucket, p.amount, p.option.label) for p in rec.parts] == [(1, D(1500), "Konto A")]


def test_recommendation_overflow_goes_to_best_safe_long_term_option() -> None:
    rec = invest.recommend(inputs(surplus=D(6000)), S, SAFE)
    assert [(p.bucket, p.amount, p.option.label) for p in rec.parts] == [
        (1, D(5000), "Konto A"),
        (3, D(1000), "EDO"),  # ETF jest ryzykowny — nie jest polecany automatycznie
    ]


def test_deficit_recommends_no_new_deposits() -> None:
    rec = invest.recommend(inputs(surplus=D(-200)), S, SAFE)
    assert rec.state == "deficit" and rec.parts == []


def test_no_projection_means_no_data() -> None:
    assert invest.recommend(inputs(surplus=None), S, SAFE).state == "no_data"


# --- zapis i ustawienia ---


def test_settings_roundtrip_and_validation(conn: sqlite3.Connection) -> None:
    assert invest.load_settings(conn) == invest.Settings()
    invest.save_settings(conn, "6", "1; 5; 8", "0,3", "2,5")
    got = invest.load_settings(conn)
    assert got.cushion_months == 6 and got.etf_returns == (D(1), D(5), D(8))
    assert got.etf_ter == D("0.3") and got.inflation == D("2.5")
    with pytest.raises(invest.InvestError):
        invest.save_settings(conn, "0", "0;6;9", "0.2", "3")
    with pytest.raises(invest.InvestError):
        invest.save_settings(conn, "3", "0;6", "0.2", "3")


def test_asset_crud_and_totals(conn: sqlite3.Connection) -> None:
    a = invest.save_asset(
        conn, None, "bonds", "EDO 2025", "5000", "5,6", "2025-03-01", "2035-03-01", True
    )
    invest.save_asset(conn, None, "etf", "ETF świat", "2 500,50", "", "", "", False)
    assert invest.assets_total(conn) == D("7500.50")
    got = next(x for x in invest.all_assets(conn) if x.id == a)
    assert got.ike and got.rate == D("5.60") and got.maturity == date(2035, 3, 1)
    invest.archive_asset(conn, a)
    assert invest.assets_total(conn) == D("2500.50")
    with pytest.raises(invest.InvestError):
        invest.save_asset(conn, None, "bonds", "", "100", "", "", "", False)
    with pytest.raises(invest.InvestError):
        invest.save_asset(conn, None, "nonsense", "X", "100", "", "", "", False)


def test_offer_crud_validates_kind_and_rate(conn: sqlite3.Connection) -> None:
    oid = invest.save_offer(conn, "deposit", "Bank A", "5,5", "", "", "12", "min. 1000 zł", False)
    got = invest.all_offers(conn)
    assert [(o.id, o.kind, o.rate, o.months) for o in got] == [(oid, "deposit", D("5.50"), 12)]
    invest.archive_offer(conn, oid)
    assert invest.all_offers(conn) == []
    with pytest.raises(invest.InvestError):
        invest.save_offer(conn, "edo", "Skarb", "6", "", "", "", "", False)  # EDO wymaga marży
    with pytest.raises(invest.InvestError):
        invest.save_offer(conn, "deposit", "Bank A", "150", "", "", "12", "", False)
    with pytest.raises(invest.InvestError):
        invest.save_offer(conn, "deposit", "Bank A", "5", "", "", "", "", False)  # lokata: okres
