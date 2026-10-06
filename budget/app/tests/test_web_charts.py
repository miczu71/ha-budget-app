"""Geometria wykresów Podsumowania (M13 E2): wycinki kołowe i słupki 12 miesięcy."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from budget.categorize.taxonomy import Category
from budget.spending import MainLine, MonthTotals
from budget.web import charts

PERIOD = "date_from=2026-09-01&date_to=2026-09-30"
KW = {"period": PERIOD, "other_href": "/spending?month=2026-09", "review_href": "/review"}


def group(cat_id: int, amount: str, count: int = 1) -> MainLine:
    cat = Category(cat_id, None, f"k{cat_id}", f"Kategoria {cat_id}", None, cat_id * 10)
    return MainLine(cat, Decimal(amount), count)


def donut(
    groups: list[MainLine], unc: str = "0", unc_count: int = 0, **extra: object
) -> list[charts.Slice]:
    return charts.donut_slices(groups, Decimal(unc), unc_count, **KW, **extra)  # type: ignore[arg-type]


def test_top_n_other_and_uncategorized() -> None:
    groups = [group(i, str(1100 - i * 100)) for i in range(2, 11)]  # 9 kategorii, malejąco
    slices = donut(groups, "50.00", 3)
    assert [s.key for s in slices[:6]] == [f"cat-{i}" for i in range(2, 8)]  # malejąco
    other, unc = slices[6], slices[7]
    assert (other.key, other.color, other.href) == ("other", "other", "/spending?month=2026-09")
    assert other.amount == Decimal("300") + Decimal("200") + Decimal("100")  # kat. 8, 9, 10
    assert other.count == 3
    assert (unc.key, unc.label, unc.count, unc.href) == ("unc", "Bez kategorii", 3, "/review")
    assert slices[0].href == f"/transactions?category=2&{PERIOD}"


def test_refunds_zero_and_empty_make_no_slices() -> None:
    assert donut([]) == []
    assert donut([group(2, "-50.00"), group(3, "0")]) == []
    only = donut([group(2, "80.00"), group(3, "-10.00")])
    assert [s.key for s in only] == ["cat-2"]  # zwrot netto nie tworzy wycinka


def test_single_slice_is_a_full_circle_without_gap() -> None:
    (s,) = donut([group(2, "10.00")])
    assert (s.start, s.length, s.pct) == (0.0, 100.0, 100)
    assert s.dash == "100.000 0.000" and s.offset == "-0.000"


def test_geometry_has_gaps_and_covers_the_circle() -> None:
    slices = donut([group(2, "50.00"), group(3, "30.00"), group(4, "20.00")], gap=1.0)
    ends = [s.start + s.length for s in slices]
    assert [round(s.start, 3) for s in slices] == [0.5, 50.5, 80.5]
    assert all(b < a for b, a in zip(ends, [s.start for s in slices[1:]], strict=False))
    assert round(slices[-1].start + slices[-1].length + 0.5, 3) == 100.0  # wraca do początku


def test_percentages_sum_to_100() -> None:
    slices = donut([group(2, "1"), group(3, "1"), group(4, "1")])  # 33,33% × 3
    assert sorted(s.pct for s in slices) == [33, 33, 34]
    wide = donut([group(i, "7.00") for i in range(2, 9)], "3.00", 1)
    assert sum(s.pct for s in wide) == 100


def test_color_is_stable_per_category_and_unique_within_chart() -> None:
    a = donut([group(3, "100"), group(5, "50")])
    b = donut([group(5, "999"), group(3, "1")])  # inna kolejność i kwoty, ta sama kategoria
    color = {s.key: s.color for s in a}
    assert color["cat-3"] == {s.key: s.color for s in b}["cat-3"] == "c4"
    # id 2 i 10 mają ten sam slot (id % 8): większy zatrzymuje go, mniejszy bierze następny wolny
    clash = {s.key: s.color for s in donut([group(2, "100"), group(10, "60")])}
    assert clash == {"cat-2": "c3", "cat-10": "c4"}
    assert len({s.color for s in donut([group(i, str(100 - i)) for i in range(2, 8)])}) == 6


def month(m: int, income: str, expenses: str, partial: bool = False) -> MonthTotals:
    return MonthTotals(date(2026, m, 1), Decimal(income), Decimal(expenses), partial)


def test_nice_ceiling_and_labels() -> None:
    assert [charts.nice_ceiling(v) for v in (0, 0.5, 1, 1.1, 12345, 21000, 60000, 99999)] == [
        1.0, 1.0, 1.0, 2.0, 20000.0, 25000.0, 100000.0, 100000.0,
    ]  # fmt: skip
    chart = charts.month_bars([month(8, "100", "900")], date(2026, 8, 1))
    assert [t.label for t in chart.ticks] == ["0", "500", "1k"]
    assert [round(t.y, 1) for t in chart.ticks] == [
        148.0,
        78.0,
        8.0,
    ]  # zero na linii bazowej, maksimum na szczycie skali
    big = charts.month_bars([month(8, "0", "21000")], date(2026, 8, 1))
    assert [t.label for t in big.ticks] == ["0", "12.5k", "25k"]


def test_bars_selection_partial_href_and_heights() -> None:
    rows = [month(7, "5000", "2000"), month(8, "0", "0"), month(9, "100", "5000", partial=True)]
    chart = charts.month_bars(rows, date(2026, 8, 1))
    jul, aug, sep = chart.bars
    assert [b.selected for b in chart.bars] == [False, True, False]
    assert [b.partial for b in chart.bars] == [False, False, True]
    assert (jul.label, aug.label, sep.label) == ("lip", "sie", "wrz")
    assert sep.href == "/?month=2026-09"
    assert jul.income_h == 140.0 and sep.expenses_h == 140.0  # wspólna skala: 5000 = pełna wysokość
    assert aug.income_h == aug.expenses_h == 0.0 and not chart.bars[1].income
    assert 0 < sep.income_h < 3  # 100 zł przy skali 5000
    assert jul.x < jul.slot_x + jul.slot_w and jul.slot_x < aug.slot_x < sep.slot_x


def test_tiny_value_is_still_visible_and_empty_chart_has_axes() -> None:
    chart = charts.month_bars([month(8, "10000", "0"), month(9, "0.01", "0")], date(2026, 9, 1))
    assert chart.bars[1].income_h == 1.0  # minimum, żeby słupek nie zniknął
    empty = charts.month_bars([month(9, "0", "0")], date(2026, 9, 1))
    assert not empty.has_data and len(empty.ticks) == 3 and chart.has_data


def line(values: list[str], buffer: str = "0") -> charts.LineChart:
    days = [(date(2026, 10, 3 + i), Decimal(v)) for i, v in enumerate(values)]
    return charts.forecast_line(days, Decimal(buffer))


def test_forecast_line_marks_lowest_point_and_zero() -> None:
    c = line(["500", "100", "-200", "300"])
    xs = [float(p.split(",")[0]) for p in c.points.split()]
    ys = [float(p.split(",")[1]) for p in c.points.split()]
    assert len(ys) == 4 and xs == sorted(xs)
    assert c.low_y == pytest.approx(max(ys), abs=0.1) and c.low_x == pytest.approx(xs[2], abs=0.1)
    assert c.zero_y is not None and ys[1] < c.zero_y < ys[2]
    assert c.buffer_y is None
    assert [t.label for t in c.ticks] == ["−200", "500"]
    big = line(["5210.89", "-2627", "100"])
    assert [t.label for t in big.ticks] == ["−2,63k", "5,21k"]
    assert [text for _, text in c.x_labels] == ["dziś", "06.10"]


def test_forecast_line_buffer_only_when_in_scale_and_flat_series() -> None:
    assert line(["9000", "8000"], buffer="1000").buffer_y is None  # poza skalą
    assert line(["900", "300"], buffer="500").buffer_y is not None
    flat = line(["1000", "1000", "1000"])
    assert flat.zero_y is None and len(flat.points.split()) == 3
    assert len(line(["50"]).points.split()) == 1  # ostatni dzień miesiąca: jeden punkt
