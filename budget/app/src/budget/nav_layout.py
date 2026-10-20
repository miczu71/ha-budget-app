"""Zakładki u góry (M28): kolejność i ukrywanie; „Podsumowanie” zawsze pierwsze."""

from __future__ import annotations

from typing import NamedTuple

from budget.layout import Layout

KEY = "nav_layout"


class Tab(NamedTuple):
    label: str
    path: str  # względem `base`
    pages: tuple[str, ...]  # strony, na których zakładka świeci się jako aktywna


TABS: dict[str, Tab] = {  # domyślna kolejność
    "home": Tab("Podsumowanie", "/", ("home",)),
    "budget": Tab("Budżet", "/budget", ("budget",)),
    "piggy": Tab("Oszczędności", "/piggy", ("piggy",)),
    "loan": Tab("Kredyt", "/loan", ("loan",)),
    "invest": Tab("Inwestycje", "/invest", ("invest",)),
    "networth": Tab("Majątek", "/networth", ("networth",)),
    "year": Tab("Rok", "/year", ("year",)),
    "spending": Tab("Wydatki", "/spending", ("spending",)),
    "card": Tab("Karta", "/card", ("card",)),
    "ask": Tab("Zapytaj", "/ask", ("ask",)),
    "recurring": Tab("Cykliczne", "/recurring", ("recurring", "series")),
    "transactions": Tab("Transakcje", "/transactions", ("transactions",)),
}

layout = Layout(KEY, {k: t.label for k, t in TABS.items()}, pinned=("home",))
