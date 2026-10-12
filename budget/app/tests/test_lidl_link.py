"""Paragony Lidl Plus: odczyt pliku i dopasowanie do płatności (M29 E4)."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from budget import lidl_link

from .test_categorize_engine import add, conn, sid

__all__ = ["conn"]


def _file(tmp_path: Path, *receipts: dict[str, object]) -> Path:
    path = tmp_path / "receipts.json"
    path.write_text(json.dumps({"version": 1, "receipts": list(receipts)}), encoding="utf-8")
    return path


def _r(rid: str, day: str, paid: float, **parts: float) -> dict[str, object]:
    return {
        "id": rid,
        "day": day,
        "paid": paid,
        "url_path": f"/paragony/{rid}",
        "parts": parts or {"food": paid},
    }


def test_load_parses_receipts_and_skips_broken(tmp_path: Path) -> None:
    path = _file(tmp_path, _r("a", "2026-09-02", 12.5, food=10.0, drugstore=2.5), {"id": "zly"})
    (receipt,) = lidl_link.load(path)
    assert (
        receipt.id == "a" and receipt.day == date(2026, 9, 2) and receipt.paid == Decimal("12.50")
    )
    assert receipt.parts == {"food": Decimal("10.00"), "drugstore": Decimal("2.50")}
    assert lidl_link.load(tmp_path / "brak.json") == []
    (tmp_path / "zepsuty.json").write_text("{", encoding="utf-8")
    assert lidl_link.load(tmp_path / "zepsuty.json") == []


def test_match_links_unique_amount_and_date(conn: sqlite3.Connection, tmp_path: Path) -> None:
    hit = add(conn, "-12.50", "card", "LIDL SKLEP X POL", day="2026-09-03")
    add(conn, "-12.50", "card", "SKLEP Y POL", day="2026-09-03")  # inny sklep, ta sama kwota
    add(conn, "-30.00", "card", "LIDL SKLEP X POL", day="2026-09-20")  # poza oknem ±3 dni
    twin_a = add(conn, "-7.00", "card", "LIDL SKLEP X POL", day="2026-09-05")
    twin_b = add(conn, "-7.00", "card", "LIDL SKLEP X POL", day="2026-09-06")
    receipts = lidl_link.load(
        _file(
            tmp_path,
            _r("a", "2026-09-02", 12.5),
            _r("b", "2026-09-10", 30.0),
            _r("c", "2026-09-05", 7.0),
            _r("gotowka", "2026-09-04", 99.0),
        )
    )
    result = lidl_link.match(conn, receipts)
    assert (result.linked, result.ambiguous, result.unmatched) == (1, 1, 2)
    assert lidl_link.links(conn) == {hit: ("a", "auto")}
    assert lidl_link.candidates(conn, receipts[2]) == [twin_a, twin_b]
    again = lidl_link.match(conn, receipts)  # paragon użyty raz; ponowny przebieg nic nie dubluje
    assert again.linked == 0 and lidl_link.links(conn) == {hit: ("a", "auto")}


def test_two_receipts_same_amount_stay_unlinked(conn: sqlite3.Connection, tmp_path: Path) -> None:
    add(conn, "-9.99", "card", "LIDL SKLEP X POL", day="2026-09-03")
    receipts = lidl_link.load(
        _file(tmp_path, _r("a", "2026-09-02", 9.99), _r("b", "2026-09-04", 9.99))
    )
    assert lidl_link.match(conn, receipts).linked == 0


def test_category_map_defaults_and_validation(conn: sqlite3.Connection) -> None:
    m = lidl_link.category_map(conn)
    assert m == {
        "food": sid(conn, "spozywcze"), "drugstore": sid(conn, "drogeria"),
        "kids": sid(conn, "dzieci-zakupy"), "nonfood": sid(conn, "zakupy-inne"),
    }  # fmt: skip
    lidl_link.set_category_map(conn, {**m, "nonfood": sid(conn, "drogeria")})
    assert lidl_link.category_map(conn)["nonfood"] == sid(conn, "drogeria")


def test_service_links_after_sync_without_file_is_quiet(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    from types import SimpleNamespace

    from budget.service import Service

    svc = SimpleNamespace(
        conn=conn, settings=SimpleNamespace(lidl_receipts_path=tmp_path / "brak.json")
    )
    assert Service.link_lidl(svc) == lidl_link.MatchResult(0, 0, 0)  # type: ignore[arg-type]


def test_linked_receipt_splits_transaction_once(conn: sqlite3.Connection, tmp_path: Path) -> None:
    from budget import split
    from budget.categorize import engine

    t = add(conn, "-20.00", "card", "LIDL SKLEP X POL", day="2026-09-03")
    single = add(conn, "-8.00", "card", "LIDL SKLEP X POL", day="2026-09-12")
    mine = add(conn, "-5.00", "card", "LIDL SKLEP X POL", day="2026-09-20")
    engine.recategorize(conn)
    engine.set_manual(conn, mine, sid(conn, "restauracje"))  # decyzja użytkownika zostaje
    receipts = lidl_link.load(
        _file(
            tmp_path,
            _r("a", "2026-09-02", 20.0, food=12.0, drugstore=6.0, nonfood=2.0),
            _r("b", "2026-09-12", 8.0, drugstore=8.0),
            _r("c", "2026-09-20", 5.0, kids=5.0),
        )
    )
    lidl_link.set_category_map(
        conn, {**lidl_link.category_map(conn), "nonfood": sid(conn, "drogeria")}
    )
    assert lidl_link.match(conn, receipts).linked == 3
    assert split.get(
        conn, t
    ) == [  # nonfood zmapowane na drogerię: części sumują się per podkategoria
        (sid(conn, "spozywcze"), Decimal("-12.00")),
        (sid(conn, "drogeria"), Decimal("-8.00")),
    ]
    assert (
        conn.execute("SELECT source FROM txn_split WHERE txn_id = ?", (t,)).fetchone()[0] == "lidl"
    )
    row = conn.execute(
        "SELECT category_id, category_source FROM txn WHERE id = ?", (single,)
    ).fetchone()
    assert (row[0], row[1]) == (
        sid(conn, "drogeria"),
        "manual",
    )  # jedna kategoria = zwykła kategoria
    row = conn.execute("SELECT category_id FROM txn WHERE id = ?", (mine,)).fetchone()
    assert row[0] == sid(conn, "restauracje") and split.get(conn, mine) == []


def test_choose_links_ambiguous_receipt(conn: sqlite3.Connection, tmp_path: Path) -> None:
    from budget import split

    a = add(conn, "-7.00", "card", "LIDL SKLEP X POL", day="2026-09-05")
    b = add(conn, "-7.00", "card", "LIDL SKLEP X POL", day="2026-09-06")
    receipts = lidl_link.load(_file(tmp_path, _r("c", "2026-09-05", 7.0, food=4.0, kids=3.0)))
    assert lidl_link.match(conn, receipts).ambiguous == 1
    assert [r.id for r in lidl_link.receipts_for_txn(conn, receipts, b)] == ["c"]
    lidl_link.choose(conn, b, receipts[0])
    assert lidl_link.links(conn) == {b: ("c", "chosen")} and len(split.get(conn, b)) == 2
    assert lidl_link.receipts_for_txn(conn, receipts, a) == []  # paragon już użyty
