"""Przepływ pieniędzy okresu (M19): wpływy → grupy budżetu → kategorie główne.

Dane dla wykresu Sankey na ekranie „Wydatki” (`docs/PLAN_M19.md`). Liczby pochodzą z
`spending.sums` (te same co ekran Wydatki, podział M29 już uwzględniony); tu tylko układ węzłów
i krawędzi, bez geometrii. Zasady:
- lewa kolumna: „Wpływy” (przychody + wpływy bez kategorii) i, gdy wydano więcej, „Z oszczędności /
  deficyt”; środek: grupy (stałe, elastyczne, nieregularne, oszczędności), „Bez kategorii”
  i „Nadwyżka”; prawa: kategorie główne w grupie (top `TOP` łącznie, reszta „Inne” per grupa);
- kategoria z ujemnym netto (zwrot > wydatki) nie tworzy węzła; `excluded` jest pomijane;
- każdy węzeł ma wejścia równe wyjściom (poza lewą i prawą kolumną), deficyt rozkłada się
  proporcjonalnie na wszystkie węzły środka.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from budget import spending
from budget.categorize import taxonomy

ZERO = Decimal(0)
CENT = Decimal("0.01")
TOP = 8
PALETTE = 8
GROUPS = (
    ("fixed", "Stałe"),
    ("flexible", "Elastyczne"),
    ("non_monthly", "Nieregularne"),
    ("savings", "Oszczędności"),
)


@dataclass(frozen=True)
class Node:
    key: str  # in, deficit, g-<grupa>, unc, surplus, cat-<id>-<grupa>, other-<grupa>
    label: str
    column: int  # 0 źródła, 1 grupy, 2 kategorie
    amount: Decimal
    color: str  # klasa CSS: c1…c8, other, unc, in, deficit, surplus, g-<grupa>
    category_id: int | None = None  # kategoria główna (link do transakcji)
    group: str | None = None
    count: int = 0


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    amount: Decimal


@dataclass
class Flow:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    income: Decimal = ZERO
    outflow: Decimal = ZERO  # wydatki + oszczędności + bez kategorii
    deficit: Decimal = ZERO
    surplus: Decimal = ZERO

    def node(self, key: str) -> Node:
        return next(n for n in self.nodes if n.key == key)


@dataclass
class _Item:
    main: taxonomy.Category
    group: str
    amount: Decimal
    count: int


def _items(conn: sqlite3.Connection, s: spending.Sums) -> tuple[list[_Item], Decimal]:
    """Kategorie główne × grupa z dodatnim netto oraz przychody z kategorii."""
    items: list[_Item] = []
    income = ZERO
    for main in taxonomy.tree(conn):
        by_group: dict[str, list[tuple[Decimal, set[int]]]] = {}
        for leaf in main.children:
            acc = s.by_leaf.get(leaf.id)
            if acc is None or leaf.flex_group in (None, "excluded"):
                continue
            if leaf.flex_group == "income":
                income += max(acc.amount, ZERO)
            else:
                by_group.setdefault(leaf.flex_group, []).append((-acc.amount, acc.ids))
        for group, parts in by_group.items():
            amount = sum((p[0] for p in parts), ZERO)
            if amount > ZERO:
                ids = set().union(*(p[1] for p in parts))
                items.append(_Item(main.category, group, amount, len(ids)))
    return items, income


def _slot(cat_id: int, used: set[int]) -> int:
    slot = cat_id % PALETTE
    while slot in used:
        slot = (slot + 1) % PALETTE
    used.add(slot)
    return slot


def build(conn: sqlite3.Connection, start: date, end: date) -> Flow:
    s = spending.sums(conn, start, end)
    items, cat_income = _items(conn, s)
    flow = Flow(income=cat_income + s.unc_in.amount)

    items.sort(key=lambda i: i.amount, reverse=True)
    used: set[int] = set()
    colors = {id(i): f"c{_slot(i.main.id, used) + 1}" for i in items[:TOP]}
    names = dict(GROUPS)

    group_nodes: list[Node] = []
    cat_nodes: list[Node] = []
    edges: list[Edge] = []
    for group, _ in GROUPS:
        mine = [i for i in items if i.group == group]
        if not mine:
            continue
        rest = [i for i in mine if id(i) not in colors]
        for i in mine:
            if id(i) in colors:
                key = f"cat-{i.main.id}-{group}"
                cat_nodes.append(
                    Node(key, i.main.name, 2, i.amount, colors[id(i)], i.main.id, group, i.count)
                )
                edges.append(Edge(f"g-{group}", key, i.amount))
        if rest:
            amount = sum((i.amount for i in rest), ZERO)
            key = f"other-{group}"
            cat_nodes.append(
                Node(key, "Inne", 2, amount, "other", None, group, sum(i.count for i in rest))
            )
            edges.append(Edge(f"g-{group}", key, amount))
        total = sum((i.amount for i in mine), ZERO)
        group_nodes.append(
            Node(
                f"g-{group}",
                names[group],
                1,
                total,
                f"g-{group}",
                None,
                group,
                sum(i.count for i in mine),
            )
        )

    unc = s.unc_out.amount
    if unc > ZERO:
        group_nodes.append(Node("unc", "Bez kategorii", 1, unc, "unc", None, None, s.unc_out.count))
    flow.outflow = sum((n.amount for n in group_nodes), ZERO)
    if flow.outflow > flow.income:
        flow.deficit = flow.outflow - flow.income
    else:
        flow.surplus = flow.income - flow.outflow
        if flow.surplus > ZERO:
            group_nodes.append(Node("surplus", "Nadwyżka", 1, flow.surplus, "surplus"))

    sources: list[Node] = []
    if flow.income > ZERO:
        sources.append(Node("in", "Wpływy", 0, flow.income, "in", count=s.unc_in.count))
    if flow.deficit > ZERO:
        sources.append(Node("deficit", "Z oszczędności / deficyt", 0, flow.deficit, "deficit"))

    # krawędzie źródło → środek: przy deficycie wpływy dzielą się proporcjonalnie na wszystkie węzły
    left = flow.income
    for idx, n in enumerate(group_nodes):
        if flow.deficit > ZERO:
            last = idx == len(group_nodes) - 1
            from_in = left if last else (n.amount * flow.income / flow.outflow).quantize(CENT)
            from_in = min(from_in, n.amount, left)
            left -= from_in
            if from_in > ZERO:
                flow.edges.append(Edge("in", n.key, from_in))
            if n.amount - from_in > ZERO:
                flow.edges.append(Edge("deficit", n.key, n.amount - from_in))
        else:
            flow.edges.append(Edge("in", n.key, n.amount))
    flow.edges += edges
    flow.nodes = sources + group_nodes + cat_nodes
    return flow
