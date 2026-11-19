"""Paragony Lidl Plus: odczyt pliku i dopasowanie do płatności (M29 E4)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from budget import lidl_link

from .test_categorize_engine import add, conn, sid

__all__ = ["conn"]


def _file(tmp_path: Path, *receipts: dict[str, object]) -> Path:
    path = tmp_path / "receipts.json"
    path.write_text(json.dumps({"version": 1, "receipts": list(receipts)}), encoding="utf-8")
    return path


def _status(conn: sqlite3.Connection, txn_id: int) -> str:
    return str(
        conn.execute("SELECT status FROM txn_lidl WHERE txn_id = ?", (txn_id,)).fetchone()[0]
    )


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
    assert lidl_link.links(conn) == {hit: "a"} and _status(conn, hit) == "auto"
    path = tmp_path / "receipts.json"
    assert [r.id for r in lidl_link.receipts_for_txn(conn, path, twin_a)] == ["c"]
    assert [r.id for r in lidl_link.receipts_for_txn(conn, path, twin_b)] == ["c"]
    again = lidl_link.match(conn, receipts)  # paragon użyty raz; ponowny przebieg nic nie dubluje
    assert again.linked == 0 and lidl_link.links(conn) == {hit: "a"}


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
    path = tmp_path / "receipts.json"
    assert [r.id for r in lidl_link.receipts_for_txn(conn, path, b)] == ["c"]
    lidl_link.choose(conn, b, receipts[0])
    assert lidl_link.links(conn) == {b: "c"} and _status(conn, b) == "chosen"
    assert len(split.get(conn, b)) == 2
    assert lidl_link.receipts_for_txn(conn, path, a) == []  # paragon już użyty


def test_cash_receipt_is_skipped_and_unlink_remembers_pair(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    from budget import split

    t = add(conn, "-20.00", "card", "LIDL SKLEP X POL", day="2026-09-03")
    cash = {**_r("g", "2026-09-02", 20.0, food=20.0), "payment": "Gotówka"}
    card = {**_r("k", "2026-09-03", 20.0, food=10.0, kids=10.0), "payment": "Karta"}
    receipts = lidl_link.load(_file(tmp_path, cash, card))
    assert lidl_link.match(conn, receipts).linked == 1 and lidl_link.links(conn) == {t: "k"}
    lidl_link.unlink(conn, t)
    assert lidl_link.links(conn) == {} and split.get(conn, t) == []
    assert lidl_link.match(conn, receipts).linked == 0  # odrzucona para nie wraca


def _foreign(rid: str, day: str, paid: float, **parts: float) -> dict[str, object]:
    return {**_r(rid, day, paid, **parts), "country": "CZ", "currency": "CZK", "paid_orig": 175.4}


def test_load_without_new_fields_is_polish(tmp_path: Path) -> None:
    (r,) = lidl_link.load(_file(tmp_path, _r("a", "2026-09-02", 12.5)))
    assert (r.country, r.currency, r.paid_orig) == ("PL", "PLN", None)
    (f,) = lidl_link.load(_file(tmp_path, _foreign("f", "2026-09-02", 30.0)))
    assert (f.country, f.currency, f.paid_orig) == ("CZ", "CZK", Decimal("175.40"))
    bad = {**_r("b", "2026-09-02", 5.0), "country": 5, "paid_orig": "x"}
    (b,) = lidl_link.load(_file(tmp_path, bad))
    assert (b.country, b.paid_orig) == ("PL", None)


def test_foreign_receipt_matches_within_tolerance(conn: sqlite3.Connection, tmp_path: Path) -> None:
    t = add(conn, "-31.20", "card", "LIDL Miasto A", day="2026-09-03")  # 4% więcej
    receipts = lidl_link.load(_file(tmp_path, _foreign("f", "2026-09-02", 30.0)))
    assert lidl_link.match(conn, receipts).linked == 1
    assert lidl_link.links(conn) == {t: "f"}


def test_foreign_receipt_outside_tolerance_not_linked(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    t = add(conn, "-31.80", "card", "LIDL Miasto A", day="2026-09-03")  # 6% więcej
    receipts = lidl_link.load(_file(tmp_path, _foreign("f", "2026-09-02", 30.0)))
    assert lidl_link.match(conn, receipts).linked == 0
    assert lidl_link.receipts_for_txn(conn, tmp_path / "receipts.json", t) == []


def test_foreign_two_candidates_ambiguous(conn: sqlite3.Connection, tmp_path: Path) -> None:
    add(conn, "-30.50", "card", "LIDL Miasto A", day="2026-09-03")
    add(conn, "-29.80", "card", "LIDL Miasto A", day="2026-09-04")
    receipts = lidl_link.load(_file(tmp_path, _foreign("f", "2026-09-02", 30.0)))
    res = lidl_link.match(conn, receipts)
    assert (res.linked, res.ambiguous) == (0, 1)


def test_polish_receipt_still_exact(conn: sqlite3.Connection, tmp_path: Path) -> None:
    add(conn, "-31.00", "card", "LIDL Miasto A", day="2026-09-03")
    receipts = lidl_link.load(_file(tmp_path, _r("a", "2026-09-02", 30.0)))
    assert lidl_link.match(conn, receipts).linked == 0


def test_foreign_parts_scaled_to_bank_amount(conn: sqlite3.Connection, tmp_path: Path) -> None:
    from budget import split

    t = add(conn, "-31.00", "card", "LIDL Miasto A", day="2026-09-03")
    receipts = lidl_link.load(
        _file(tmp_path, _foreign("f", "2026-09-02", 30.0, food=20.0, drugstore=7.0, kids=3.0))
    )
    assert lidl_link.match(conn, receipts).linked == 1
    parts = split.get(conn, t)
    assert len(parts) == 3 and sum(a for _, a in parts) == Decimal("-31.00")


def test_foreign_receipt_exactly_at_tolerance_is_linked(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    add(conn, "-31.50", "card", "LIDL Miasto A", day="2026-09-03")  # dokładnie 5% więcej
    receipts = lidl_link.load(_file(tmp_path, _foreign("f", "2026-09-02", 30.0)))
    assert lidl_link.match(conn, receipts).linked == 1


def test_polish_and_foreign_receipt_claiming_one_txn_stay_manual(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    add(conn, "-30.00", "card", "LIDL Miasto A", day="2026-09-03")
    receipts = lidl_link.load(
        _file(tmp_path, _r("a", "2026-09-02", 30.0), _foreign("f", "2026-09-02", 30.0))
    )
    res = lidl_link.match(conn, receipts)
    assert (res.linked, res.ambiguous) == (0, 2)
    assert lidl_link.links(conn) == {}


def test_scaled_with_zero_total_or_no_parts_is_unchanged() -> None:
    zero = {"food": Decimal("5.00"), "deposit": Decimal("-5.00")}
    assert lidl_link._scaled(zero, Decimal("-30.00")) == zero
    assert lidl_link._scaled({}, Decimal("-30.00")) == {}


def _chain(rid: str, day: str, paid: float, chain: str, **parts: float) -> dict[str, object]:
    return {**_r(rid, day, paid, **parts), "chain": chain}


def test_load_reads_chain_and_defaults_to_lidl(tmp_path: Path) -> None:
    (a,) = lidl_link.load(_file(tmp_path, _r("a", "2026-09-02", 12.5)))
    assert a.chain == "lidl"  # stary eksport bez pola
    (b,) = lidl_link.load(_file(tmp_path, _chain("b", "2026-09-02", 5.0, "biedronka", food=5.0)))
    assert b.chain == "biedronka"


def test_load_skips_receipt_with_unknown_chain(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _file(
        tmp_path,
        _chain("c", "2026-09-02", 5.0, "zabka", food=5.0),
        _chain("d", "2026-09-02", 6.0, "lidl", food=6.0),
    )
    with caplog.at_level("WARNING"):
        assert [r.id for r in lidl_link.load(path)] == [
            "d"
        ]  # nieznanej sieci nie zgadujemy jako Lidla
    assert "nieznaną siecią" in caplog.text


def test_meta_cache_follows_file_change(tmp_path: Path) -> None:
    path = _file(tmp_path, _chain("a", "2026-09-02", 5.0, "lidl", food=5.0))
    assert lidl_link.chains(path, {"a"}) == {"a": "lidl"}
    _file(tmp_path, _chain("a", "2026-09-02", 5.0, "biedronka", food=5.0))
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))  # nowy eksport = nowy mtime
    assert lidl_link.chains(path, {"a"}) == {"a": "biedronka"}
    assert lidl_link.chains(tmp_path / "brak.json", {"a"}) == {}


def test_biedronka_receipt_links_biedronka_expense(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    t = add(conn, "-15.40", "card", "BIEDRONKA 1234 POL", day="2026-09-03")
    j = add(conn, "-8.10", "card", "JERONIMO MARTINS POLSKA SA", day="2026-09-03")
    receipts = lidl_link.load(
        _file(
            tmp_path,
            _chain("b1", "2026-09-02", 15.4, "biedronka", food=15.4),
            _chain("b2", "2026-09-02", 8.1, "biedronka", food=8.1),
        )
    )
    assert lidl_link.match(conn, receipts).linked == 2
    assert lidl_link.links(conn) == {t: "b1", j: "b2"}


def test_receipt_never_links_other_chain(conn: sqlite3.Connection, tmp_path: Path) -> None:
    bio_t = add(conn, "-12.50", "card", "BIEDRONKA 1 POL", day="2026-09-03")
    lidl_only = _file(tmp_path, _r("l", "2026-09-02", 12.5))
    assert lidl_link.match(conn, lidl_link.load(lidl_only)).linked == 0  # Lidl ≠ Biedronka
    assert lidl_link.receipts_for_txn(conn, lidl_only, bio_t) == []
    add(conn, "-9.90", "card", "LIDL SKLEP X POL", day="2026-09-05")
    bio_paragon = _file(tmp_path, _chain("b", "2026-09-05", 9.9, "biedronka", food=9.9))
    assert lidl_link.match(conn, lidl_link.load(bio_paragon)).linked == 0  # Biedronka ≠ Lidl
    assert lidl_link.links(conn) == {}


def test_same_amount_both_chains_each_pairs_own(conn: sqlite3.Connection, tmp_path: Path) -> None:
    lidl_t = add(conn, "-12.50", "card", "LIDL SKLEP X POL", day="2026-09-03")
    bio_t = add(conn, "-12.50", "card", "BIEDRONKA 1 POL", day="2026-09-03")
    receipts = lidl_link.load(
        _file(
            tmp_path,
            _r("l", "2026-09-02", 12.5),
            _chain("b", "2026-09-02", 12.5, "biedronka", food=12.5),
        )
    )
    assert lidl_link.match(conn, receipts).linked == 2
    assert lidl_link.links(conn) == {lidl_t: "l", bio_t: "b"}


def test_receipts_for_txn_filters_by_expense_chain(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    bio_t = add(conn, "-7.00", "card", "BIEDRONKA 1 POL", day="2026-09-05")
    path = _file(
        tmp_path,
        _r("l", "2026-09-05", 7.0),
        _chain("b", "2026-09-05", 7.0, "biedronka", food=7.0),
    )
    assert [r.id for r in lidl_link.receipts_for_txn(conn, path, bio_t)] == ["b"]


def test_chains_maps_receipt_ids_to_chain(tmp_path: Path) -> None:
    path = _file(
        tmp_path,
        _r("l", "2026-09-02", 12.5),
        _chain("b", "2026-09-02", 5.0, "biedronka", food=5.0),
    )
    assert lidl_link.chains(path, {"l", "b", "x"}) == {"l": "lidl", "b": "biedronka"}
    assert lidl_link.chains(tmp_path / "brak.json", {"l"}) == {}
    assert lidl_link.chains(path, set()) == {}
