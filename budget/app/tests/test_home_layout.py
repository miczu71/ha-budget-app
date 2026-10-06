"""M16: układ kafelków strony głównej."""

from __future__ import annotations

import sqlite3

from budget import home_layout as H
from budget.storage import db

from .test_categorize_engine import conn

__all__ = ["conn"]


def _keys(conn: sqlite3.Connection) -> list[str]:
    return [t.key for t in H.load(conn)]


def test_default_layout_is_all_visible_in_default_order(conn: sqlite3.Connection) -> None:
    tiles = H.load(conn)
    assert [t.key for t in tiles] == list(H.TILES)
    assert not any(t.hidden for t in tiles)


def test_move_swaps_neighbours_and_ignores_edges(conn: sqlite3.Connection) -> None:
    H.move(conn, "inbox", -1)
    assert _keys(conn)[:3] == ["forecast", "inbox", "spending"]
    H.move(conn, "inbox", -1)
    H.move(conn, "inbox", -1)  # już pierwszy
    assert _keys(conn)[0] == "inbox"
    H.move(conn, "months", 1)  # już ostatni
    assert _keys(conn)[-1] == "months"


def test_toggle_hides_and_shows(conn: sqlite3.Connection) -> None:
    H.toggle(conn, "card")
    assert {t.key for t in H.load(conn) if t.hidden} == {"card"}
    H.toggle(conn, "card")
    assert not any(t.hidden for t in H.load(conn))


def test_reset_restores_default(conn: sqlite3.Connection) -> None:
    H.move(conn, "recent", -3)
    H.toggle(conn, "balance")
    H.reset(conn)
    assert _keys(conn) == list(H.TILES) and not any(t.hidden for t in H.load(conn))


def test_load_drops_unknown_keys_and_appends_new_tiles(conn: sqlite3.Connection) -> None:
    db.kv_set(conn, H.KEY, {"order": ["recent", "gone", "inbox"], "hidden": ["gone", "inbox"]})
    tiles = H.load(conn)
    assert [t.key for t in tiles[:2]] == ["recent", "inbox"]
    assert [t.key for t in tiles[2:]] == [k for k in H.TILES if k not in ("recent", "inbox")]
    assert [t.key for t in tiles if t.hidden] == ["inbox"]
