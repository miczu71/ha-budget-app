"""Geometria wykresów Podsumowania (M13 E2): wycinki kołowe i słupki 12 miesięcy."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from budget import flow
from budget.categorize.taxonomy import Category
from budget.spending import MainLine, MonthTotals
from budget.web import charts

from .test_recurring_schedule import make_event

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


def test_forecast_line_zone_covers_below_zero_only() -> None:
    mixed = line(["500", "100", "-200", "300"])
    assert mixed.zone_y == mixed.zero_y
    assert line(["500", "100", "300"]).zone_y is None
    assert line(["-500", "-100"]).zone_y == charts.TOP  # całe saldo poniżej zera


def test_forecast_line_marks_all_inflows_and_three_largest_outflows() -> None:
    days = [
        (date(2026, 10, 3 + i), Decimal(v))
        for i, v in enumerate(["900", "800", "850", "300", "250", "240"])
    ]
    events = [
        make_event(1, 4, "-100"),
        make_event(2, 5, "50"),
        make_event(3, 6, "-550"),
        make_event(4, 7, "-50"),
        make_event(5, 7, "-10"),
        make_event(6, 8, "-250"),
    ]
    c = charts.forecast_line(days, Decimal(0), events)
    assert [(m.kind, m.name) for m in c.marks] == [
        ("out", "Seria 1"),
        ("in", "Seria 2"),
        ("out", "Seria 3"),
        ("out", "Seria 6"),
    ]  # dwa najmniejsze wydatki bez znacznika
    ys = [float(p.split(",")[1]) for p in c.points.split()]
    assert [m.y for m in c.marks] == pytest.approx([ys[1], ys[2], ys[3], ys[5]], abs=0.1)


def test_forecast_line_low_label_and_payday_label() -> None:
    c = line(["500", "100", "-200", "300"])
    assert c.low_day == date(2026, 10, 5) and c.low_anchor == "middle"
    assert line(["-200", "100", "300", "400"]).low_anchor == "start"
    assert line(["500", "400", "300", "-200"]).low_anchor == "end"
    days = [(date(2026, 10, 3 + i), Decimal(v)) for i, v in enumerate(["500", "100"])]
    assert (
        charts.forecast_line(days, Decimal(0), (), date(2026, 10, 4)).x_labels[-1][1]
        == "wypłata 04.10"
    )


def test_networth_line_marks_approx_points_and_zero() -> None:
    from datetime import date as d

    c = charts.networth_line(
        [
            (d(2026, 8, 31), Decimal(-100), True),
            (d(2026, 9, 30), Decimal(300), True),
            (d(2026, 10, 20), Decimal(500), False),
        ]
    )
    assert [p.approx for p in c.dots] == [True, True, False]
    assert c.dots[0].y > c.dots[2].y and c.zero_y is not None
    assert c.x_labels == [(c.dots[0].x, "sie 26"), (c.dots[2].x, "paź 26")]
    assert len(c.points.split()) == 3


def sk(f: flow.Flow) -> charts.SankeyChart:
    return charts.sankey(f, **KW)  # type: ignore[arg-type]


def node(key: str, col: int, amount: str, **kw: object) -> flow.Node:
    return flow.Node(key, key, col, Decimal(amount), kw.pop("color", "c1"), **kw)  # type: ignore[arg-type]


def test_sankey_empty_flow() -> None:
    chart = sk(flow.Flow())
    assert chart.nodes == [] and chart.links == []


def test_sankey_min_height_fit_and_links() -> None:
    f = flow.Flow(
        nodes=[
            node("in", 0, "1000"),
            node("g-fixed", 1, "999"),
            node("unc", 1, "1", color="unc"),
            node("cat-1-fixed", 2, "998", category_id=1),
            node("other-fixed", 2, "1", color="other"),
        ],
        edges=[
            flow.Edge("in", "g-fixed", Decimal(999)),
            flow.Edge("in", "unc", Decimal(1)),
            flow.Edge("g-fixed", "cat-1-fixed", Decimal(998)),
            flow.Edge("g-fixed", "other-fixed", Decimal(1)),
        ],
    )
    chart = sk(f)
    nodes = {n.key: n for n in chart.nodes}
    assert nodes["unc"].h >= charts.SK_MIN_H and not nodes["unc"].show_label
    assert nodes["g-fixed"].show_label
    assert all(n.y + n.h <= chart.height for n in chart.nodes)
    assert nodes["cat-1-fixed"].href == f"/transactions?category=1&{PERIOD}"
    assert nodes["other-fixed"].href == KW["other_href"] and nodes["unc"].href == "/review"
    assert len(chart.links) == 4 and all(lk.d.startswith("M") for lk in chart.links)
    # węzły jednej kolumny nie nachodzą na siebie
    col1 = sorted((n for n in chart.nodes if n.column == 1), key=lambda n: n.y)
    assert col1[0].y + col1[0].h <= col1[1].y


def test_sankey_label_clipped() -> None:
    f = flow.Flow(
        nodes=[node("in", 0, "10"), node("g-fixed", 1, "10"), node("c", 2, "10", category_id=2)],
        edges=[flow.Edge("in", "g-fixed", Decimal(10)), flow.Edge("g-fixed", "c", Decimal(10))],
    )
    f.nodes[2] = flow.Node("c", "Kategoria o bardzo rozbudowanej nazwie", 2, Decimal(10), "c1", 2)
    n = {n.key: n for n in sk(f).nodes}["c"]
    assert len(n.label) <= charts.SK_CHARS[2] and n.label.endswith("…")
    assert n.full_label == "Kategoria o bardzo rozbudowanej nazwie"


def item(key: str, amount: str, count: int = 1, drill: str = "") -> charts.Item:
    return charts.Item(key, f"Pozycja {key}", Decimal(amount), count, f"/t/{key}", drill)


def test_drill_slices_top_six_then_rest_as_other() -> None:
    items = [item(f"i{n}", str(100 - n)) for n in range(8)]  # 100 … 93, już malejąco
    slices = charts.drill_slices(items, other_href="/t?cat=1")
    assert [s.key for s in slices] == ["i0", "i1", "i2", "i3", "i4", "i5", "other"]
    assert [s.color for s in slices] == ["c1", "c2", "c3", "c4", "c5", "c6", "other"]
    other = slices[-1]
    assert other.label == "Pozostałe" and other.amount == Decimal("187") and other.count == 2
    assert other.href == "/t?cat=1" and other.drill == ""
    assert sum(s.pct for s in slices) == 100


def test_drill_slices_sorted_and_keep_drill_of_items() -> None:
    slices = charts.drill_slices(
        [item("small", "10"), item("big", "90", drill="cat=5&sub=7")], other_href="/o"
    )
    assert [s.key for s in slices] == ["big", "small"]
    assert slices[0].drill == "cat=5&sub=7" and slices[1].drill == ""
    assert slices[0].href == "/t/big" and slices[0].pct == 90


def test_drill_slices_skip_non_positive_and_empty_total() -> None:
    assert charts.drill_slices([item("a", "0"), item("b", "-5")], other_href="/o") == []
    only = charts.drill_slices([item("a", "0"), item("b", "-5"), item("c", "10")], other_href="/o")
    assert [s.key for s in only] == ["c"] and only[0].pct == 100 and only[0].length == 100.0


def test_donut_drill_only_for_categories() -> None:
    slices = donut([group(2, "80"), group(4, "200"), group(6, "10")], "40", top=2)
    assert {s.key: s.drill for s in slices} == {
        "cat-4": "cat=4",
        "cat-2": "cat=2",
        "other": "",
        "unc": "",
    }
