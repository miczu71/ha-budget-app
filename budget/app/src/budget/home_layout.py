"""Układ kafelków strony głównej (M16): kolejność i ukrywanie, wspólne dla wszystkich urządzeń."""

from __future__ import annotations

from budget.layout import Layout

KEY = "home_layout"

TILES: dict[str, str] = {  # domyślna kolejność
    "forecast": "Prognoza do wypłaty",
    "month": "Zostało w miesiącu",
    "spending": "Gdzie poszły pieniądze",
    "inbox": "Do decyzji",
    "balance": "Bilans miesiąca",
    "card": "Karta kredytowa",
    "piggy": "Skarbonki",
    "savings": "Oszczędności",
    "networth": "Majątek netto",
    "year": "Rok",
    "upcoming": "Co jeszcze zejdzie",
    "recent": "Ostatnie transakcje",
    "months": "Ostatnie 12 miesięcy",
}


_LAYOUT = Layout(KEY, TILES)
load = _LAYOUT.load
move = _LAYOUT.move
toggle = _LAYOUT.toggle
reset = _LAYOUT.reset
