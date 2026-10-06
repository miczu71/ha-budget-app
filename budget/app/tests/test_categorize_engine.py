"""Silnik kategorii i reguły na księdze syntetycznej."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from decimal import Decimal

import pytest

from budget import ledger
from budget.categorize import engine, rules, taxonomy
from budget.categorize.rules import Conditions, Rule, RuleError, TextCondition
from budget.storage import db
from budget.storage.db import now_iso


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = db.connect(":memory:")
    now = now_iso()
    c.execute(
        "INSERT INTO account (id, kind, iban, currency, created_at) "
        "VALUES (1, 'current', 'PL00111122223333444455556666', 'PLN', ?)",
        (now,),
    )
    c.execute(
        "INSERT INTO account (id, kind, currency, created_at) VALUES (2, 'card', 'PLN', ?)", (now,)
    )
    yield c
    c.close()


def add(
    conn: sqlite3.Connection,
    amount: str,
    kind: str = "card",
    description: str = "",
    counterparty: str | None = None,
    *,
    day: str = "2026-09-10",
    account: int = 1,
    source: str = "eb",
    **extra: object,
) -> int:
    now = now_iso()
    cols = {
        "account_id": account,
        "status": "BOOK",
        "booking_date": day,
        "tx_date": day,
        "amount": amount,
        "currency": "PLN",
        "description": description,
        "counterparty_name": counterparty,
        "kind": kind,
        "kind_source": "csv",
        "fingerprint": f"fp{amount}{description}{day}{counterparty}",
        "source": source,
        "first_seen_at": now,
        "updated_at": now,
        **extra,
    }
    cur = conn.execute(
        f"INSERT INTO txn ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        list(cols.values()),
    )
    return int(cur.lastrowid or 0)


def cat(conn: sqlite3.Connection, txn_id: int) -> tuple[str | None, str | None, str]:
    r = conn.execute(
        "SELECT c.slug, t.category_source, t.merchant FROM txn t "
        "LEFT JOIN category c ON c.id = t.category_id WHERE t.id = ?",
        (txn_id,),
    ).fetchone()
    return r["slug"], r["category_source"], r["merchant"]


def sid(conn: sqlite3.Connection, slug: str) -> int:
    return taxonomy.by_slug(conn)[slug].id


def rule(conn: sqlite3.Connection, slug: str, *conds: tuple[str, str, str], **kw: object) -> int:
    r = Rule(
        None,
        sid(conn, slug),
        Conditions(text=tuple(TextCondition(*c) for c in conds), **kw),  # type: ignore[arg-type]
    )
    return rules.save(conn, r)


def test_sources_in_order(conn: sqlite3.Connection) -> None:
    lidl = add(conn, "-50.00", "card", "LIDL UL. X XYZ POL 2026-09-10")
    cash = add(conn, "-200.00", "cash", "", "BANKOMAT XYZ 123")
    fee = add(conn, "-9.90", "fee", "PROWIZJA")
    loan = add(conn, "-1500.00", "loan", "SPLATA RATY KREDYTU")
    unknown = add(conn, "-30.00", "card", "SKLEP ABC XYZ POL 2026-09-10")
    transfer = add(conn, "-500.00", "transfer_out", "", "LIDL", transfer_group="t1")
    person = add(conn, "-100.00", "transfer_out", "Netflix", "JAN NOWAK")
    assert engine.recategorize(conn) == 7
    assert cat(conn, lidl) == ("spozywcze", "dictionary", "Lidl")
    assert cat(conn, cash)[:2] == ("wyplaty-gotowki", "dictionary")  # BANKOMAT — słowo ogólne
    assert cat(conn, fee)[:2] == ("oplaty-bankowe", "kind")
    assert cat(conn, loan)[:2] == ("kredyt", "kind")
    assert cat(conn, unknown) == (None, None, "Sklep")
    assert cat(conn, transfer)[:2] == (None, None)
    assert cat(conn, person) == (None, None, "Jan Nowak")  # tytuł przelewu nie kategoryzuje
    assert engine.recategorize(conn) == 0  # deterministyczne


def test_rule_beats_dictionary_and_priority(conn: sqlite3.Connection) -> None:
    t = add(conn, "-50.00", "card", "LIDL UL. X XYZ POL 2026-09-10")
    first = rule(conn, "restauracje", ("merchant", "equals", "lidl"))
    second = rule(conn, "dzieci-zakupy", ("description", "contains", "lidl"))  # na górze
    engine.recategorize(conn)
    assert cat(conn, t)[:2] == ("dzieci-zakupy", "rule")
    rules.move(conn, second, +1)
    engine.recategorize(conn)
    assert cat(conn, t)[:2] == ("restauracje", "rule")
    rules.set_enabled(conn, first, False)
    engine.recategorize(conn)
    assert cat(conn, t)[:2] == ("dzieci-zakupy", "rule")
    hits = {r.id: r.hits for r in rules.all_rules(conn)}
    assert hits == {first: 0, second: 1}


def test_rule_conditions_and_rename(conn: sqlite3.Connection) -> None:
    rent = add(conn, "-2000.00", "standing_order", "Czynsz", "WSPOLNOTA ABC")
    small = add(conn, "-20.00", "standing_order", "Fundusz", "WSPOLNOTA ABC")
    income = add(conn, "2000.00", "transfer_in", "Zwrot", "WSPOLNOTA ABC")
    rule(
        conn,
        "media",
        ("counterparty_name", "starts_with", "wspólnota"),
        direction="out",
        amount_min=Decimal("100"),
    )
    rid = rules.all_rules(conn)[0].id
    assert rid is not None
    r = rules.get(conn, rid)
    assert r is not None
    rules.save(conn, Rule(rid, r.category_id, r.conditions, rename="  Czynsz  "))
    engine.recategorize(conn)
    assert cat(conn, rent) == ("media", "rule", "Czynsz")
    assert cat(conn, small) == (None, None, "Wspolnota Abc")
    assert cat(conn, income)[0] is None


def test_counterparty_account_ignores_spaces(conn: sqlite3.Connection) -> None:
    t = add(
        conn,
        "-100.00",
        "transfer_out",
        "Opłata",
        "JAN NOWAK",
        counterparty_account="PL 61 1090 1014 0000 0712 1981 2874",
    )
    rule(conn, "szkola-zajecia", ("counterparty_account", "equals", "PL61109010140000071219812874"))
    engine.recategorize(conn)
    assert cat(conn, t)[0] == "szkola-zajecia"


def test_manual_wins_and_reset(conn: sqlite3.Connection) -> None:
    t = add(conn, "-50.00", "card", "LIDL UL. X XYZ POL 2026-09-10")
    engine.set_manual(conn, t, sid(conn, "prezenty"))
    rule(conn, "restauracje", ("merchant", "equals", "Lidl"))
    engine.recategorize(conn)
    assert cat(conn, t)[:2] == ("prezenty", "manual")
    engine.set_manual(conn, t, None)
    engine.recategorize(conn)
    assert cat(conn, t)[:2] == ("restauracje", "rule")


def test_set_manual_errors(conn: sqlite3.Connection) -> None:
    t = add(conn, "-500.00", "transfer_out", "", "X", transfer_group="t1")
    with pytest.raises(taxonomy.TaxonomyError, match="Przelew"):
        engine.set_manual(conn, t, sid(conn, "prezenty"))
    u = add(conn, "-5.00", "card", "X")
    with pytest.raises(taxonomy.TaxonomyError, match="podkategori"):
        engine.set_manual(conn, u, 2)  # kategoria główna
    with pytest.raises(taxonomy.TaxonomyError, match="transakcji"):
        engine.set_manual(conn, 999, None)


def test_refund_inherits_final_purchase_category(conn: sqlite3.Connection) -> None:
    buy = add(conn, "-100.00", "card", "SKLEP ABC XYZ POL 2026-09-01")
    back = add(conn, "40.00", "card_refund", "SKLEP ABC XYZ POL 2026-09-05", refund_of=buy)
    engine.recategorize(conn)
    assert cat(conn, back)[:2] == (None, None)  # zakup bez kategorii — zwrot też
    engine.set_manual(conn, buy, sid(conn, "ubrania"))
    engine.recategorize(conn)
    assert cat(conn, back)[:2] == ("ubrania", "refund")


def test_preview_matches_saved_result(conn: sqlite3.Connection) -> None:
    a = add(conn, "-30.00", "card", "KEBAB ABC XYZ POL 2026-09-01", day="2026-09-01")
    b = add(conn, "-25.00", "card", "KEBAB DEF XYZ POL 2026-09-03", day="2026-09-03")
    m = add(conn, "-20.00", "card", "KEBAB GHI XYZ POL 2026-09-04", day="2026-09-04")
    add(conn, "-10.00", "card", "SKLEP XYZ POL 2026-09-04")
    engine.set_manual(conn, m, sid(conn, "prezenty"))
    older = rule(conn, "restauracje", ("description", "contains", "kebab def"))
    engine.recategorize(conn)
    assert {r.id for r in rules.all_rules(conn)} == {older}
    rules.move(conn, older, -1)

    candidate = Rule(
        None,
        sid(conn, "dostawy-jedzenia"),
        Conditions(text=(TextCondition("description", "contains", "kebab"),)),
    )
    p = engine.preview(conn, candidate)
    # nowa reguła ląduje na górze, więc wygrywa także z „kebab def”
    assert (p.matches, p.applied, p.manual_skipped, p.shadowed) == (3, 2, 1, 0)
    assert p.total == Decimal("-75.00")
    assert [s.txn_id for s in p.samples] == [m, b, a]
    before = {t: cat(conn, t)[0] for t in (a, b, m)}
    rules.save(conn, candidate)
    engine.recategorize(conn)
    after = {t: cat(conn, t)[0] for t in (a, b, m)}
    assert sum(before[t] != after[t] for t in before) == p.changes == 2


def test_preview_edit_in_place_and_shadowed(conn: sqlite3.Connection) -> None:
    t = add(conn, "-30.00", "card", "KEBAB ABC XYZ POL 2026-09-01")
    top = rule(conn, "restauracje", ("description", "contains", "kebab"))
    low = rule(conn, "prezenty", ("description", "contains", "abc"))
    rules.move(conn, low, +1)  # `low` pod `top`
    engine.recategorize(conn)
    r = rules.get(conn, low)
    assert r is not None
    p = engine.preview(conn, r)
    assert (p.matches, p.applied, p.shadowed, p.changes) == (1, 0, 1, 0)
    r_top = rules.get(conn, top)
    assert r_top is not None
    p = engine.preview(conn, Rule(top, sid(conn, "spozywcze"), r_top.conditions))
    assert (p.applied, p.changes) == (1, 1)
    assert cat(conn, t)[0] == "restauracje"  # podgląd niczego nie zapisuje


def test_drop_csv_txn_keeps_manual_category(conn: sqlite3.Connection) -> None:
    old = add(conn, "-30.00", "card", "SKLEP ABC", source="csv")
    new = add(conn, "-30.00", "card", "SKLEP ABC XYZ")
    engine.set_manual(conn, old, sid(conn, "prezenty"))
    ledger._drop_csv_txn(conn, old, new)
    engine.recategorize(conn)
    assert cat(conn, new)[:2] == ("prezenty", "manual")


def test_validate_rule(conn: sqlite3.Connection) -> None:
    leaf = sid(conn, "prezenty")
    cases: list[tuple[Rule, str]] = [
        (Rule(None, leaf), "co najmniej jednego"),
        (
            Rule(None, leaf, Conditions(text=(TextCondition("merchant", "contains", "  "),))),
            "co najmniej",
        ),
        (
            Rule(None, leaf, Conditions(text=(TextCondition("merchant", "contains", "!!"),))),
            "liter",
        ),
        (Rule(None, leaf, Conditions(text=(TextCondition("iban", "contains", "x"),))), "Nieznane"),
        (
            Rule(None, 2, Conditions(text=(TextCondition("merchant", "contains", "x"),))),
            "podkategori",
        ),
        (
            Rule(
                None,
                leaf,
                Conditions(
                    text=(TextCondition("merchant", "contains", "x"),),
                    amount_min=Decimal(10),
                    amount_max=Decimal(5),
                ),
            ),
            "od",
        ),
        (
            Rule(
                None,
                leaf,
                Conditions(text=(TextCondition("merchant", "contains", "x"),), account_id=9),
            ),
            "konta",
        ),
        (
            Rule(
                None,
                leaf,
                Conditions(
                    text=tuple(TextCondition("merchant", "contains", "x") for _ in range(4))
                ),
            ),
            "Najwyżej",
        ),
    ]
    for r, message in cases:
        with pytest.raises(RuleError, match=message):
            rules.validate(conn, r)


def test_conditions_json_roundtrip() -> None:
    c = Conditions(
        text=(TextCondition("merchant", "equals", "Lidl"),),
        account_id=2,
        kind="card",
        direction="out",
        amount_min=Decimal("10.00"),
        amount_max=None,
    )
    assert Conditions.from_json(c.to_json()) == c


@pytest.mark.parametrize(
    ("raw", "value"), [("", None), (" 1 234,5 ", Decimal("1234.50")), ("-7", Decimal("7.00"))]
)
def test_parse_amount(raw: str, value: Decimal | None) -> None:
    assert rules.parse_amount(raw) == value
    with pytest.raises(RuleError):
        rules.parse_amount("abc")


def test_delete_rule_releases_transactions(conn: sqlite3.Connection) -> None:
    t = add(conn, "-30.00", "card", "SKLEP ABC")
    rid = rule(conn, "prezenty", ("merchant", "contains", "sklep"))
    engine.recategorize(conn)
    rules.delete(conn, rid)
    engine.recategorize(conn)
    assert cat(conn, t)[:2] == (None, None)


def _naive(txns: list[engine._Txn], all_: list[Rule]) -> dict[int, Rule | None]:
    """Referencja: pierwsza pasująca aktywna reguła po kolei (zachowanie sprzed indeksu)."""
    active = [r for r in all_ if r.enabled]
    return {t.id: next((r for r in active if r.conditions.matches(t.facts)), None) for t in txns}


def test_rule_index_same_as_linear_scan(conn: sqlite3.Connection) -> None:
    add(conn, "-50.00", "card", "LIDL UL. X XYZ POL 2026-09-10")
    add(conn, "-12.00", "card", "LIDL UL. Y XYZ POL 2026-09-11", account=2)
    add(conn, "-30.00", "card", "SKLEP ĄBC XYZ POL 2026-09-10")
    add(conn, "-300.00", "card", "SKLEP ĄBC XYZ POL 2026-09-12")
    add(conn, "40.00", "card", "SKLEP ĄBC XYZ POL 2026-09-13")
    add(conn, "-100.00", "transfer_out", "Składka", "JXNA QWERTOWSKA")
    add(conn, "100.00", "transfer_in", "Zwrot", "JXNA QWERTOWSKA")
    add(conn, "-80.00", "transfer_out", "Opłata", "ŻÓŁW SPÓŁKA", counterparty_account="PL 11 2222")
    add(conn, "-9.00", "card", "KAWIARNIA ZETA XYZ POL 2026-09-14")
    rule(conn, "restauracje", ("merchant", "equals", "kawiarnia zeta"))
    rule(conn, "media", ("counterparty_account", "contains", "PL112222"))
    rule(conn, "dzieci-zakupy", ("merchant", "equals", "sklep abc"), amount_min=Decimal("100"))
    rule(conn, "spozywcze", ("merchant", "equals", "SKLEP ABC"), direction="out")
    rule(conn, "media", ("merchant", "equals", "Jxna Qwertowska"), direction="in")
    rule(conn, "restauracje", ("merchant", "equals", "Jxna Qwertowska"), direction="out")
    rule(conn, "media", ("description", "contains", "skladka"))  # wyżej niż equals na osobę
    rule(conn, "dzieci-zakupy", ("merchant", "equals", "lidl"), account_id=2)
    off = rule(conn, "media", ("merchant", "equals", "lidl"))
    rules.set_enabled(conn, off, False)
    rule(conn, "spozywcze", ("merchant", "starts_with", "kawiar"), ("merchant", "equals", "x"))
    engine.recategorize(conn)
    txns = engine._load(conn, engine.merchants.builtin())
    all_ = rules.all_rules(conn)
    index = engine._RuleIndex(all_)
    assert {t.id: index.first(t.facts) for t in txns} == _naive(txns, all_)
    # kolejność odwrócona: equals wyżej niż contains
    reversed_ = [replace(r, priority=-r.priority) for r in reversed(all_)]
    index = engine._RuleIndex(reversed_)
    assert {t.id: index.first(t.facts) for t in txns} == _naive(txns, reversed_)


def test_facts_for_selected_txns(conn: sqlite3.Connection) -> None:
    lidl = add(conn, "-50.00", "card", "LIDL UL. X XYZ POL 2026-09-10")
    jan = add(conn, "-40.00", "transfer_out", "Składka IX", "JAN TESTOWSKI", account=2)
    add(conn, "-9.90", "fee", "PROWIZJA")
    got = engine.facts(conn, [lidl, jan, 999])
    assert set(got) == {lidl, jan}
    assert got[lidl].merchant == "Lidl" and got[lidl].amount == Decimal("-50.00")
    assert got[jan].merchant == "Jan Testowski" and got[jan].account_id == 2
    assert got[jan].description == "Składka IX" and got[jan].kind == "transfer_out"
    cond = Conditions(text=(TextCondition("description", "contains", "skladka"),))
    assert cond.matches(got[jan]) and not cond.matches(got[lidl])
    assert engine.facts(conn, []) == {}


def test_clean_conditions_without_category(conn: sqlite3.Connection) -> None:
    cond = Conditions(text=(TextCondition("merchant", "contains", "  ab   c "),))
    assert rules.clean_conditions(conn, cond).text[0].value == "ab c"
    with pytest.raises(RuleError, match="co najmniej jednego"):
        rules.clean_conditions(conn, Conditions(text=()))
    with pytest.raises(RuleError, match="Wybierz podkategorię"):
        rules.validate(conn, Rule(None, 0, cond))


def test_learned_from_consistent_manual_decisions(conn: sqlite3.Connection) -> None:
    first = add(conn, "-30.00", "card", "SKLEP ABC XYZ POL 2026-09-01")
    second = add(conn, "-45.00", "card", "SKLEP ABC XYZ POL 2026-09-05")
    income = add(conn, "45.00", "card_refund", "SKLEP ABC XYZ POL 2026-09-06")
    lidl = add(conn, "-50.00", "card", "LIDL UL. X XYZ POL 2026-09-10")
    engine.set_manual(conn, first, sid(conn, "ubrania"))
    engine.set_manual(conn, lidl, sid(conn, "prezenty"))
    lidl2 = add(conn, "-20.00", "card", "LIDL UL. X XYZ POL 2026-09-12")
    engine.recategorize(conn)
    assert cat(conn, second) == ("ubrania", "learned", "Sklep")
    assert cat(conn, income)[:2] == (None, None)  # inny kierunek — osobna pamięć
    assert cat(conn, lidl2)[:2] == ("spozywcze", "dictionary")  # pamięć tylko wypełnia luki
    other = add(conn, "-10.00", "card", "SKLEP ABC XYZ POL 2026-09-08")
    engine.set_manual(conn, other, sid(conn, "prezenty"))  # niezgodne decyzje — bez pamięci
    engine.recategorize(conn)
    assert cat(conn, second)[:2] == (None, None)


def test_refund_inherits_learned_purchase_category(conn: sqlite3.Connection) -> None:
    buy = add(conn, "-100.00", "card", "SKLEP ABC XYZ POL 2026-09-01")
    old = add(conn, "-30.00", "card", "SKLEP ABC XYZ POL 2026-08-01")
    back = add(conn, "40.00", "card_refund", "SKLEP ABC XYZ POL 2026-09-05", refund_of=buy)
    engine.set_manual(conn, old, sid(conn, "ubrania"))
    engine.recategorize(conn)
    assert cat(conn, buy) == ("ubrania", "learned", "Sklep")
    assert cat(conn, back)[:2] == ("ubrania", "refund")


def test_set_manual_counts_learned_decisions(conn: sqlite3.Connection) -> None:
    ids = [add(conn, f"-{n}.00", "card", "SKLEP ABC XYZ POL 2026-09-01") for n in (10, 20, 30)]
    engine.set_manual(conn, ids[0], sid(conn, "ubrania"))
    engine.recategorize(conn)
    engine.set_manual(conn, ids[1], sid(conn, "ubrania"))
    engine.set_manual(conn, ids[2], sid(conn, "prezenty"))
    engine.set_manual(conn, ids[0], sid(conn, "prezenty"))  # ręczna, nie z pamięci
    assert db.kv_get(conn, engine.LEARNED_STATS_KEY) == {"confirmed": 1, "corrected": 1}
