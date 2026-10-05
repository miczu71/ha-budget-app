"""Budżet Flex (M5a): kwota od miesiąca, co liczy się do „wydane”, tempo, mediany, grupy."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget import flex
from budget.categorize import engine, taxonomy
from budget.categorize.rules import Conditions, TextCondition
from budget.categorize.taxonomy import TaxonomyError
from budget.recurring import series as S
from budget.snapshot import Snapshot

from .test_categorize_engine import add, conn, sid

__all__ = ["conn"]


def build(
    c: sqlite3.Connection, month: str = "2026-09-01", today: str = "2026-09-10"
) -> flex.FlexMonth:
    engine.recategorize(c)
    return flex.build(Snapshot(c), date.fromisoformat(month), date.fromisoformat(today))


def test_budget_applies_from_month_until_next_change(conn: sqlite3.Connection) -> None:
    assert flex.budget_for(conn, date(2026, 9, 1)) is None
    flex.set_budget(conn, date(2026, 8, 15), Decimal("2000"))
    flex.set_budget(conn, date(2026, 10, 1), Decimal("3000"))
    assert flex.budget_for(conn, date(2026, 7, 1)) is None
    assert flex.budget_for(conn, date(2026, 9, 20)) == (Decimal("2000.00"), date(2026, 8, 1))
    assert flex.budget_for(conn, date(2027, 1, 1)) == (Decimal("3000.00"), date(2026, 10, 1))
    flex.set_budget(conn, date(2026, 8, 1), Decimal("2100"))  # ten sam miesiąc → nadpisanie
    assert flex.budget_for(conn, date(2026, 9, 1)) == (Decimal("2100.00"), date(2026, 8, 1))


@pytest.mark.parametrize("value", ["", "0", "-5", "abc", "10000000"])
def test_parse_amount_rejects(value: str) -> None:
    with pytest.raises(flex.FlexError):
        flex.parse_amount(value)


def test_parse_amount_polish_format() -> None:
    assert flex.parse_amount("2\xa0500,50") == Decimal("2500.50")
    assert flex.parse_amount(" 3000 ") == Decimal("3000.00")


def test_what_counts_as_spent(conn: sqlite3.Connection) -> None:
    buy = add(conn, "-100.00", "card", "LIDL XYZ POL", day="2026-09-02")
    add(conn, "20.00", "card_refund", "LIDL XYZ POL", day="2026-09-05", refund_of=buy)
    add(conn, "-40.00", "card", "SKLEP ABC XYZ", day="2026-09-04")  # bez kategorii
    add(conn, "15.00", "transfer_in", "Zwrot", "OSOBA X", day="2026-09-04")  # wpływ bez kat.
    fixed = add(conn, "-300.00", "transfer_out", "Prad", "DOSTAWCA", day="2026-09-06")
    once = add(conn, "-500.00", "card", "SKLEP RTV", day="2026-09-07")
    sav = add(conn, "-1000.00", "transfer_out", "Lokata", "JA SAM", day="2026-09-08")
    add(conn, "5000.00", "transfer_in", "Pensja", "FIRMA X", day="2026-09-09")
    add(conn, "-700.00", "card_repayment", "", None, day="2026-09-09", transfer_group="t1")
    add(conn, "-9.00", "card", "LIDL XYZ", day="2026-09-09", currency="EUR")
    engine.set_manual(conn, fixed, sid(conn, "media"))
    engine.set_manual(conn, once, sid(conn, "elektronika"))
    engine.set_manual(conn, sav, sid(conn, "oszczednosci-przelewy"))
    f = build(conn)

    assert f.spent == Decimal("120.00")  # 100 − 20 zwrotu + 40 bez kategorii
    assert (f.uncategorized, f.uncategorized_count) == (Decimal("40.00"), 1)
    assert (f.fixed, f.non_monthly) == (Decimal("300.00"), Decimal("500.00"))
    assert f.other_currency == 1
    assert [(line.category.slug, line.amount, line.count) for line in f.lines] == [
        ("spozywcze", Decimal("80.00"), 2)
    ]
    assert f.lines[0].parent == "Jedzenie"
    assert f.budget is None and f.remaining is None and f.per_day is None


def test_pace_and_per_day(conn: sqlite3.Connection) -> None:
    add(conn, "-120.00", "card", "LIDL XYZ POL", day="2026-09-02")
    flex.set_budget(conn, date(2026, 9, 1), Decimal("3000"))
    f = build(conn)  # 10 września, wrzesień ma 30 dni
    assert (f.days_in_month, f.day, f.days_left) == (30, 10, 21)
    assert f.remaining == Decimal("2880.00")
    assert f.expected == Decimal("1000.00")
    assert not f.over_pace
    assert f.per_day == Decimal("137.14")  # 2880 / 21
    assert f.elapsed == pytest.approx(1 / 3)

    last = build(conn, today="2026-09-30")
    assert last.days_left == 1 and last.per_day == last.remaining

    add(conn, "-1500.00", "card", "BIEDRONKA XYZ", day="2026-09-09")
    f = build(conn)
    assert f.over_pace and f.used == pytest.approx(1620 / 3000)

    add(conn, "-2000.00", "card", "BIEDRONKA ABC", day="2026-09-09")
    f = build(conn)
    assert f.remaining == Decimal("-620.00") and f.per_day == Decimal("0.00")


def test_past_month_has_no_pace(conn: sqlite3.Connection) -> None:
    add(conn, "-120.00", "card", "LIDL XYZ POL", day="2026-09-02")
    flex.set_budget(conn, date(2026, 9, 1), Decimal("100"))
    f = build(conn, today="2026-10-05")
    assert f.day is None and not f.is_current
    assert (f.days_left, f.per_day, f.expected, f.elapsed) == (0, None, None, 1.0)
    assert f.remaining == Decimal("-20.00")
    assert f.next_month == date(2026, 10, 1)


def test_history_medians_and_suggestion(conn: sqlite3.Connection) -> None:
    # historia od lipca: 2 pełne miesiące przed wrześniem
    add(conn, "-100.00", "card", "LIDL A POL", day="2026-07-03")
    add(conn, "-300.00", "card", "LIDL B POL", day="2026-08-03")
    add(conn, "-80.00", "card", "ORLEN STACJA A", day="2026-08-04")  # paliwo tylko w sierpniu
    add(conn, "-50.00", "card", "LIDL C POL", day="2026-09-03")
    f = build(conn)
    assert [h.month for h in f.history] == [date(2026, 7, 1), date(2026, 8, 1)]
    assert [h.spent for h in f.history] == [Decimal("100.00"), Decimal("380.00")]
    assert [h.uncategorized for h in f.history] == [0, 0]
    assert f.suggested == Decimal("240")  # mediana 240
    lines = {line.category.slug: line for line in f.lines}
    assert lines["spozywcze"].median == Decimal("200.00")
    assert lines["paliwo"].median == Decimal("40.00")  # lipiec liczy się jako 0
    assert lines["paliwo"].amount == 0 and lines["paliwo"].count == 0

    add(conn, "-1.00", "card", "LIDL D POL", day="2026-06-03")  # 3 miesiące: 1, 100, 380
    assert build(conn).suggested == Decimal("100")
    add(conn, "-5.00", "card", "LIDL E POL", day="2026-07-04")
    assert build(conn).suggested == Decimal("110")  # mediana 105 → w górę do 10 zł


def test_no_history_no_suggestion(conn: sqlite3.Connection) -> None:
    add(conn, "-50.00", "card", "LIDL C POL", day="2026-09-03")
    f = build(conn)
    assert f.history == [] and f.suggested is None
    assert f.lines[0].median == 0


def test_flex_group_change_moves_amount(conn: sqlite3.Connection) -> None:
    bill = add(conn, "-300.00", "transfer_out", "Prad", "DOSTAWCA", day="2026-09-06")
    engine.set_manual(conn, bill, sid(conn, "media"))
    assert build(conn).spent == 0
    cat = taxonomy.set_flex_group(conn, sid(conn, "media"), "flexible")
    assert cat.slug == "media"
    f = build(conn)
    assert (f.spent, f.fixed) == (Decimal("300.00"), Decimal("0"))
    with pytest.raises(TaxonomyError, match="tylko podkategoria"):
        taxonomy.set_flex_group(conn, sid(conn, "dom"), "flexible")
    with pytest.raises(TaxonomyError, match="Nieznana"):
        taxonomy.set_flex_group(conn, sid(conn, "media"), "inne")


# --- pula z dochodu (etap 3, decyzja 14) --------------------------------------------------------


def pay(c: sqlite3.Connection, amount: str, month: str, src: str = "FIRMA X") -> int:
    """Wpływ z podkategorii „Wynagrodzenie” 24. dnia miesiąca `RRRR-MM`."""
    t = add(c, amount, "transfer_in", f"Wynagrodzenie {month}", src, day=f"{month}-24")
    engine.set_manual(c, t, sid(c, "wynagrodzenie"))
    return t


def bill(c: sqlite3.Connection, amount: str, month: str) -> None:
    t = add(c, f"-{amount}", "transfer_out", f"Prad {month}", "DOSTAWCA", day=f"{month}-05")
    engine.set_manual(c, t, sid(c, "media"))


def months(start: str, n: int) -> list[str]:
    d = date.fromisoformat(f"{start}-01")
    return [
        f"{(d.year * 12 + d.month - 1 + i) // 12}-{(d.month - 1 + i) % 12 + 1:02d}"
        for i in range(n)
    ]


def test_auto_pool_is_previous_month_income_minus_fixed_median(conn: sqlite3.Connection) -> None:
    for m, fixed in zip(
        months("2026-03", 6), ["300", "300", "500", "300", "300", "900"], strict=True
    ):
        pay(conn, "9000.00", m)
        bill(conn, fixed, m)
    add(conn, "200.00", "transfer_in", "Zwrot", "OSOBA X", day="2026-08-10")  # bez kategorii
    f = build(conn)  # wrzesień: wypłata z sierpnia
    assert f.budget_source == "auto" and f.budget_from is None
    a = f.auto
    assert a is not None and a.income_month == date(2026, 8, 1)
    assert (a.income, a.bonus, a.fixed, a.fixed_months) == (
        Decimal("9000.00"),
        Decimal("0"),
        Decimal("300.00"),
        6,
    )
    assert a.amount == f.budget == Decimal("8700.00")
    assert a.drop is None


def test_lower_salary_lowers_next_month_pool_and_hints_threshold(
    conn: sqlite3.Connection,
) -> None:
    for m in months("2026-01", 6):  # styczeń–czerwiec 9000, od lipca 6500
        pay(conn, "9000.00", m)
    pay(conn, "6500.00", "2026-07")
    july = build(conn, month="2026-07-01", today="2026-07-10")
    assert july.budget == Decimal("9000.00") and july.auto and july.auto.drop is None
    aug = build(conn, month="2026-08-01", today="2026-08-10")
    assert aug.budget == Decimal("6500.00")
    assert aug.auto is not None and aug.auto.drop is not None
    source, drop = aug.auto.drop
    assert source == "Firma X" and drop == pytest.approx(2500 / 9000)


def test_bonus_above_typical_stays_outside_pool(conn: sqlite3.Connection) -> None:
    for m in months("2026-01", 3):
        pay(conn, "9000.00", m)
    pay(conn, "27000.00", "2026-04")
    pay(conn, "1500.00", "2026-04", src="URZAD Y")  # nowe źródło — w całości
    f = build(conn, month="2026-05-01", today="2026-05-10")
    a = f.auto
    assert a is not None
    assert (a.income, a.bonus) == (Decimal("28500.00"), Decimal("18000.00"))
    assert a.amount == Decimal("10500.00")  # 9000 typowe + 1500
    assert [(s.name, s.bonus) for s in a.sources] == [
        ("Firma X", Decimal("18000.00")),
        ("Urzad Y", Decimal("0")),
    ]
    assert a.drop is None  # premia nie jest „spadkiem”


def test_january_return_after_threshold_is_not_a_bonus(conn: sqlite3.Connection) -> None:
    for m in months("2025-02", 5):
        pay(conn, "9000.00", m)
    for m in months("2025-07", 6):
        pay(conn, "6500.00", m)
    pay(conn, "11000.00", "2026-01")
    f = build(conn, month="2026-02-01", today="2026-02-10")
    assert f.auto is not None and f.auto.bonus == 0
    assert f.budget == Decimal("11000.00")


def test_auto_pool_edge_cases(conn: sqlite3.Connection) -> None:
    assert build(conn).auto is None  # brak wpływów w sierpniu
    pay(conn, "1000.00", "2026-08")
    for m in months("2026-03", 6):
        bill(conn, "1500", m)
    f = build(conn)
    assert f.auto is not None and f.auto.amount == 0 and f.budget == 0  # nie poniżej zera


def test_manual_amount_overrides_and_back_to_auto(conn: sqlite3.Connection) -> None:
    for m in months("2026-06", 4):
        pay(conn, "9000.00", m)
    flex.set_budget(conn, date(2026, 8, 1), Decimal("2500"))
    f = build(conn)
    assert (f.budget, f.budget_source, f.budget_from) == (
        Decimal("2500.00"),
        "manual",
        date(2026, 8, 1),
    )
    assert f.auto is not None and f.auto.amount == Decimal("9000.00")  # widoczna obok
    flex.set_budget(conn, date(2026, 9, 1), None)  # wróć do automatycznej od września
    f = build(conn)
    assert (f.budget, f.budget_source) == (Decimal("9000.00"), "auto")
    aug = build(conn, month="2026-08-01", today="2026-09-10")
    assert aug.budget == Decimal("2500.00")  # sierpień bez zmian
    assert flex.budget_for(conn, date(2026, 10, 1)) == (None, date(2026, 9, 1))


# --- składniki stałych (etap 4, decyzja 15) -----------------------------------------------------


def spend(c: sqlite3.Connection, amount: str, month: str, slug: str) -> None:
    t = add(
        c, f"-{amount}", "transfer_out", f"{slug} {month}", f"ODBIORCA {slug}", day=f"{month}-07"
    )
    engine.set_manual(c, t, sid(c, slug))


def test_fixed_is_sum_of_subcategory_medians(conn: sqlite3.Connection) -> None:
    pay(conn, "9000.00", "2026-08")
    for i, m in enumerate(months("2026-03", 6)):
        spend(conn, "2300.00", m, "kredyt")
        if i < 3:
            spend(conn, "600.00", m, "ubezpieczenia")  # 3 z 6 mies. → mediana 300
        if i in (3, 4):
            spend(conn, "400.00", m, "media")  # 2 z 6 mies. → mediana 0
        spend(conn, "50.00", m, "noclegi")  # nieregularne — kandydat do stałych
    a = build(conn).auto
    assert a is not None
    # sumy miesięcy: 2900 ×3, 2700 ×2, 2300 → mediana sumy 2800; suma median 2300 + 300
    assert a.fixed == Decimal("2600.00")
    assert [(line.category.slug, line.median) for line in a.fixed_lines] == [
        ("kredyt", Decimal("2300.00")),
        ("ubezpieczenia", Decimal("300.00")),
    ]
    assert sum(line.median for line in a.fixed_lines) == a.fixed
    assert a.fixed_lines[0].parent  # nazwa kategorii głównej
    assert [(line.category.slug, line.median) for line in a.candidates] == [
        ("noclegi", Decimal("50.00"))
    ]


def test_fixed_lines_skip_zero_and_follow_group_change(conn: sqlite3.Connection) -> None:
    pay(conn, "9000.00", "2026-08")
    for m in months("2026-03", 6):
        spend(conn, "2300.00", m, "kredyt")
    spend(conn, "40.00", "2026-08", "media")  # 1 z 6 mies. → mediana 0, pominięta
    a = build(conn).auto
    assert a is not None and [line.category.slug for line in a.fixed_lines] == ["kredyt"]
    assert "wynagrodzenie" not in [line.category.slug for line in a.candidates]
    taxonomy.set_flex_group(conn, sid(conn, "kredyt"), "flexible")
    a = build(conn).auto
    assert a is not None and a.fixed == 0 and a.amount == Decimal("9000.00")
    assert [line.category.slug for line in a.candidates] == ["kredyt"]


# --- serie cykliczne w puli (M5b E4, decyzja 4) -------------------------------------------------


def serie(
    c: sqlite3.Connection,
    slug: str,
    amount: str,
    cadence: str = "M",
    status: str = "active",
    direction: str = "out",
) -> int:
    """Seria na odbiorcę z `spend` (`ODBIORCA <slug>`)."""
    cond = Conditions(
        text=(TextCondition("counterparty_name", "equals", f"ODBIORCA {slug}"),),
        direction=direction,
    )
    return S.insert(
        c,
        name=f"Seria {slug}",
        direction=direction,
        cadence=cadence,
        conditions=cond,
        expected=Decimal(amount),
        tolerance=Decimal("5"),
        anchor_day=7,
        status=status,
        origin="manual",
        key=None,
    )


def seed_year(c: sqlite3.Connection, slug: str, amount: str) -> None:
    for m in months("2026-03", 7):  # marzec–wrzesień
        spend(c, amount, m, slug)


def test_series_in_flexible_category_leaves_spent_and_enters_fixed(
    conn: sqlite3.Connection,
) -> None:
    pay(conn, "9000.00", "2026-08")
    seed_year(conn, "spozywcze", "50.00")
    spend(conn, "30.00", "2026-09", "paliwo")
    before = build(conn)
    assert before.spent == Decimal("80.00") and before.recurring == 0
    assert before.auto is not None and before.auto.fixed == 0
    serie(conn, "spozywcze", "50.00")
    f = build(conn)
    assert f.spent == Decimal("30.00") and f.recurring == Decimal("50.00")
    assert [line.category.slug for line in f.lines] == ["paliwo"]
    assert f.history and all(h.spent <= Decimal("30.00") for h in f.history)
    a = f.auto
    assert a is not None and a.fixed == a.fixed_series == Decimal("50.00")
    assert a.amount == Decimal("8950.00")
    assert [(line.series.name, line.monthly) for line in a.series_lines] == [
        ("Seria spozywcze", Decimal("50.00"))
    ]


def test_series_in_fixed_category_is_not_counted_twice(conn: sqlite3.Connection) -> None:
    pay(conn, "9000.00", "2026-08")
    seed_year(conn, "kredyt", "2300.00")
    assert build(conn).auto is not None and build(conn).auto.fixed == Decimal("2300.00")  # type: ignore[union-attr]
    serie(conn, "kredyt", "2300.00")
    f = build(conn)
    a = f.auto
    assert a is not None and a.fixed == Decimal("2300.00")  # seria, bez mediany kredytu
    assert a.fixed_lines == [] and len(a.series_lines) == 1
    assert f.fixed == 0 and f.recurring == Decimal("2300.00")  # „poza pulą” bez podwójnego


def test_quarterly_and_yearly_series_are_monthly_share(conn: sqlite3.Connection) -> None:
    pay(conn, "9000.00", "2026-08")
    serie(conn, "ubezpieczenia", "300.00", cadence="Q")
    serie(conn, "media", "1200.00", cadence="Y")
    a = build(conn).auto
    assert a is not None and a.fixed == Decimal("200.00")  # 100 + 100, serie bez transakcji
    assert [line.monthly for line in a.series_lines] == [Decimal("100.00")] * 2


def test_savings_series_stays_outside_pool(conn: sqlite3.Connection) -> None:
    pay(conn, "9000.00", "2026-08")
    seed_year(conn, "oszczednosci-przelewy", "500.00")
    serie(conn, "oszczednosci-przelewy", "500.00")
    f = build(conn)
    assert f.auto is not None and f.auto.series_lines == [] and f.auto.fixed == 0
    assert f.recurring == 0 and f.auto.amount == Decimal("9000.00")


def test_only_active_outgoing_series_count(conn: sqlite3.Connection) -> None:
    pay(conn, "9000.00", "2026-08")
    seed_year(conn, "spozywcze", "50.00")
    serie(conn, "spozywcze", "50.00", status="proposed")
    serie(conn, "spozywcze", "50.00", status="ended")
    serie(conn, "spozywcze", "50.00", status="rejected")
    f = build(conn)
    assert f.auto is not None and f.auto.series_lines == [] and f.recurring == 0
    assert f.spent == Decimal("50.00")  # transakcje zostają w „wydane”
    serie(conn, "wynagrodzenie", "9000.00", direction="in")
    assert build(conn).auto.series_lines == []  # type: ignore[union-attr]


def test_manual_budget_unchanged_but_spent_excludes_series(conn: sqlite3.Connection) -> None:
    seed_year(conn, "spozywcze", "50.00")
    flex.set_budget(conn, date(2026, 9, 1), Decimal("1000"))
    serie(conn, "spozywcze", "50.00")
    f = build(conn)
    assert f.budget == Decimal("1000.00") and f.spent == 0 and f.remaining == Decimal("1000.00")
