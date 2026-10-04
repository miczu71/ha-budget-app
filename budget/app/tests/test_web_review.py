"""Panel M4b: kolejka „Do przejrzenia” — grupy, podgląd, reguła, „tylko te”, grupa kraju."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest

from budget import review
from budget.categorize import engine, rules
from budget.service import Service
from budget.storage.db import now_iso

from .test_categorize_engine import add, cat, sid
from .test_web import INGRESS, _client

__all__ = ["service"]
from .test_web import service

DAY = "2026-09-10"


def _seed(conn: sqlite3.Connection) -> dict[str, int]:
    conn.execute(
        "INSERT INTO account (id, kind, currency, display_name, created_at) "
        "VALUES (1, 'current', 'PLN', 'Rachunek', ?)",
        (now_iso(),),
    )
    ids = {
        "q1": add(conn, "-30.00", "card", "QWERTY 12 XYZ POL 2026-09-01", day="2026-09-01"),
        "q2": add(conn, "-20.00", "card", "QWERTY 12 XYZ POL 2026-09-05", day="2026-09-05"),
        "p_out": add(conn, "-500.00", "transfer_out", "Prezent", "JAN TESTOWSKI", day=DAY),
        "p_in": add(conn, "100.00", "transfer_in", "Zwrot", "JAN TESTOWSKI", day=DAY),
        "ch1": add(conn, "-80.00", "card", "ZXCVB 1 XyzCHE 2026-09-10", day=DAY),
        "ch2": add(conn, "-40.00", "card", "ASDFG 2 XYZ CHE 2026-09-11", day="2026-09-11"),
        "lidl": add(conn, "-50.00", "card", "LIDL UL. X XYZ POL 2026-09-01", day="2026-09-01"),
    }
    engine.recategorize(conn)
    return ids


def _group(kind: str, value: str, direction: str = "out", gid: str = "m1") -> dict[str, str]:
    return {"kind": kind, "value": value, "direction": direction, "currency": "PLN", "gid": gid}


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


async def test_empty_queue_and_nav(client: httpx.AsyncClient) -> None:
    r = await client.get("/review")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert "Nic do przejrzenia" in r.text
    assert f'href="{INGRESS}/review"' in (await client.get("/")).text


async def test_queue_page(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)
    page = (await client.get("/review")).text
    assert "Zagranica" in page and "Szwajcaria" in page
    assert "Jan Testowski" in page and "Qwerty" in page and "Lidl" not in page
    assert page.index("Jan Testowski") < page.index("Qwerty")  # wg kwoty
    assert 'class="nav-count">6<' in page  # 5 wydatków + 1 wpływ
    by_count = (await client.get("/review?sort=count")).text
    assert by_count.index("Qwerty") < by_count.index("Jan Testowski")
    incomes = (await client.get("/review?direction=in")).text
    assert "Jan Testowski" in incomes and "Szwajcaria" not in incomes and "Qwerty" not in incomes


async def test_group_body_lazy(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    r = await client.get("/review/group", params=_group("merchant", "Qwerty"))
    assert f'value="{ids["q1"]}" checked' in r.text and 'name="only"' in r.text
    r = await client.get("/review/group", params=_group("country", "CHE", gid="c1"))
    assert "Zxcvb" in r.text and "Asdfg" in r.text and 'name="only"' not in r.text
    assert f"{INGRESS}/rules/new?txn=" in r.text
    r = await client.get("/review/group", params=_group("merchant", "Nieznany"))
    assert "już przejrzana" in r.text


async def test_assign_rule(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    leaf = sid(conn, "restauracje")
    form = {
        **_group("merchant", "Qwerty"),
        "category_id": str(leaf),
        "txn": [str(ids["q1"]), str(ids["q2"])],
    }
    p = await client.post("/review/preview", data=form)
    assert "Reguła" in p.text and "Restauracje" in p.text and "w tym 2 z tej grupy" in p.text
    r = await client.post("/review/assign", data=form)
    assert "zapisano" in r.text and "reguła" in r.text
    assert 'id="nav-pending"' in r.text and 'hx-swap-oob="true"' in r.text
    [rule] = rules.all_rules(conn)
    assert rule.conditions.direction == "out" and rule.conditions.text[0].value == "Qwerty"
    assert cat(conn, ids["q1"])[:2] == ("restauracje", "rule")
    # nowa transakcja tego sprzedawcy kategoryzuje się sama
    new = add(conn, "-25.00", "card", "QWERTY 12 XYZ POL 2026-09-20", day="2026-09-20")
    engine.recategorize(conn)
    assert cat(conn, new)[:2] == ("restauracje", "rule")
    assert review.group(conn, review.GroupKey("merchant", "Qwerty", "out", "PLN")) is None


async def test_assign_only_selected_is_manual(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    leaf = sid(conn, "prezenty")
    form = {**_group("merchant", "Qwerty"), "category_id": str(leaf), "txn": [str(ids["q1"])]}
    p = await client.post("/review/preview", data=form)
    assert "Kategoria ręczna" in p.text and "zostaną w kolejce" in p.text
    r = await client.post("/review/assign", data=form)
    assert "zapisano" in r.text and 'id="m1r"' in r.text  # reszta grupy otwarta
    assert rules.all_rules(conn) == []
    assert cat(conn, ids["q1"])[:2] == ("prezenty", "manual")
    assert cat(conn, ids["q2"])[0] is None
    # „tylko te” przy pełnym zaznaczeniu też bez reguły
    form = {
        **_group("merchant", "Qwerty"),
        "category_id": str(leaf),
        "txn": [str(ids["q2"])],
        "only": "on",
    }
    await client.post("/review/assign", data=form)
    assert rules.all_rules(conn) == [] and cat(conn, ids["q2"])[1] == "manual"


async def test_assign_direction_keeps_income_separate(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    form = {
        **_group("merchant", "Jan Testowski"),
        "category_id": str(sid(conn, "przelewy-rodzina")),
        "txn": [str(ids["p_out"])],
    }
    await client.post("/review/assign", data=form)
    assert cat(conn, ids["p_out"])[:2] == ("przelewy-rodzina", "rule")
    assert cat(conn, ids["p_in"])[0] is None  # wpływ od tej samej osoby zostaje w kolejce


async def test_assign_country_group(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    form = {
        **_group("country", "CHE", gid="c1"),
        "category_id": str(sid(conn, "podroze-inne")),
        "txn": [str(ids["ch1"]), str(ids["ch2"])],
    }
    r = await client.post("/review/assign", data=form)
    assert "zapisano" in r.text
    assert rules.all_rules(conn) == []
    assert cat(conn, ids["ch1"])[:2] == ("podroze-inne", "manual")
    assert cat(conn, ids["ch2"])[:2] == ("podroze-inne", "manual")


async def test_assign_errors(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    base = {**_group("merchant", "Qwerty"), "txn": [str(ids["q1"])]}
    r = await client.post("/review/assign", data=base)
    assert "Wybierz podkategorię" in r.text
    r = await client.post("/review/assign", data={**base, "category_id": "2"})  # kategoria główna
    assert "Wybierz podkategorię" in r.text
    leaf = str(sid(conn, "restauracje"))
    r = await client.post(
        "/review/assign", data={**_group("merchant", "Qwerty"), "category_id": leaf}
    )
    assert "Zaznacz co najmniej jedną" in r.text
    # transakcja spoza grupy (np. podmieniony formularz) — nic nie zapisane
    r = await client.post(
        "/review/assign", data={**base, "category_id": leaf, "txn": [str(ids["lidl"])]}
    )
    assert "odśwież" in r.text and cat(conn, ids["lidl"])[1] == "dictionary"
    r = await client.post(
        "/review/assign", data={**_group("merchant", "Nieznany"), "category_id": leaf}
    )
    assert "już przejrzana" in r.text


async def test_preview_warns_about_categorized_others(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    # starsza reguła łapie tylko drobne kwoty; nowa (na górze listy) przejmie też je
    cond = rules.Conditions(
        text=(rules.TextCondition("merchant", "equals", "Qwerty"),), amount_max=Decimal("25")
    )
    rules.save(conn, rules.Rule(None, sid(conn, "spozywcze"), cond))
    engine.recategorize(conn)
    assert cat(conn, ids["q2"])[1] == "rule"  # 20 zł → stara reguła; q1 (30 zł) w kolejce
    form = {
        **_group("merchant", "Qwerty"),
        "category_id": str(sid(conn, "restauracje")),
        "txn": [str(ids["q1"])],
    }
    p = await client.post("/review/preview", data=form)
    assert "Zmieni też kategorię 1 transakcji" in p.text


async def test_month_view(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    aug = add(service.conn, "-11.00", "card", "QWERTY 12 XYZ POL 2026-08-20", day="2026-08-20")
    engine.recategorize(service.conn)
    page = (await client.get("/review?month=2026-08")).text
    assert "sierpień 2026" in page and "Qwerty" in page
    assert "Jan Testowski" not in page and "Szwajcaria" not in page
    assert f'href="{INGRESS}/review?direction=out&sort=amount"' in page  # wszystkie miesiące
    assert "month=2026-08" in page and 'name="month"' not in page  # grupy leniwe
    assert 'class="nav-count">7<' in page  # licznik w nawigacji globalny
    sept = (await client.get("/review?month=2026-09&direction=in")).text
    assert "wrzesień 2026" in sept and "Jan Testowski" in sept
    assert "month=2026-09" in sept
    body = await client.get(
        "/review/group", params={**_group("merchant", "Qwerty"), "month": "2026-08"}
    )
    assert f'value="{aug}" checked' in body.text
    assert f'name="txn" value="{ids["q1"]}"' not in body.text
    assert 'name="month" value="2026-08"' in body.text


async def test_month_view_assign(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    aug = add(conn, "-11.00", "card", "QWERTY 12 XYZ POL 2026-08-20", day="2026-08-20")
    engine.recategorize(conn)
    leaf = str(sid(conn, "restauracje"))
    form = {**_group("merchant", "Qwerty"), "month": "2026-08", "category_id": leaf}
    # pozycja spoza miesiąca nie należy do grupy w tym widoku
    r = await client.post("/review/assign", data={**form, "only": "1", "txn": [str(ids["q1"])]})
    assert "Lista transakcji się zmieniła" in r.text
    p = await client.post("/review/preview", data={**form, "txn": [str(aug)]})
    assert "obejmie też 2 tr. z innych miesięcy" in p.text and "Zmieni też" not in p.text
    r = await client.post("/review/assign", data={**form, "txn": [str(aug)]})
    assert "zapisano" in r.text and "reguła" in r.text
    # reguła obejmuje cały ten sprzedawca, także wrzesień
    assert cat(conn, ids["q1"])[:2] == ("restauracje", "rule")


async def test_month_view_only_selected(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    aug = add(conn, "-11.00", "card", "QWERTY 12 XYZ POL 2026-08-20", day="2026-08-20")
    engine.recategorize(conn)
    form = {
        **_group("merchant", "Qwerty"),
        "month": "2026-09",
        "category_id": str(sid(conn, "restauracje")),
        "only": "1",
        "txn": [str(ids["q1"]), str(ids["q2"])],
    }
    r = await client.post("/review/assign", data=form)
    assert "zapisano" in r.text and "reguła" not in r.text
    assert cat(conn, ids["q1"])[1] == "manual" and cat(conn, aug)[0] is None
    assert "w kolejce w tym miesiącu: 4" in r.text  # wrzesień: 3 wydatki + 1 wpływ
    assert 'id="nav-pending" class="nav-count" hx-swap-oob="true">5<' in r.text


async def test_spending_links_to_month_queue(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)
    page = (await client.get("/spending?month=2026-09")).text
    assert f'href="{INGRESS}/review?month=2026-09"' in page
    assert f'href="{INGRESS}/review?direction=in&month=2026-09"' in page


# --- M4f/1: edytowalny tekst reguły ------------------------------------------------------------


def _chain(conn: sqlite3.Connection) -> dict[str, int]:
    """`_seed` + drugi sklep tej samej sieci pod inną nazwą sprzedawcy."""
    ids = _seed(conn)
    ids["s1"] = add(conn, "-15.00", "card", "QWERTY-SKLEP 7 XYZ POL 2026-09-03", day="2026-09-03")
    engine.recategorize(conn)
    return ids


def _put_suggestion(conn: sqlite3.Connection, merchant: str, category_id: int) -> None:
    conn.execute(
        "INSERT INTO suggestion (merchant, direction, category_id, confidence, candidates, model, "
        "created_at) VALUES (?, 'out', ?, 0.9, ?, 'm', ?)",
        (merchant, category_id, f"[[{category_id}, 0.9]]", now_iso()),
    )


async def test_group_body_has_rule_text(client: httpx.AsyncClient, service: Service) -> None:
    _chain(service.conn)
    r = await client.get("/review/group", params=_group("merchant", "Qwerty-Sklep"))
    assert 'name="rule_value_0" value="Qwerty-Sklep"' in r.text
    assert '<option value="equals" selected' in r.text and 'value="contains"' in r.text
    r = await client.get("/review/group", params=_group("country", "CHE", gid="c1"))
    assert 'name="rule_value_0"' not in r.text  # grupa kraju — bez reguły


async def test_rule_text_contains_catches_other_groups(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _chain(service.conn)
    conn = service.conn
    leaf = sid(conn, "restauracje")
    _put_suggestion(conn, "Qwerty", leaf)
    _put_suggestion(conn, "Qwerty-Sklep", sid(conn, "spozywcze"))
    form = {
        **_group("merchant", "Qwerty-Sklep"),
        "category_id": str(leaf),
        "txn": [str(ids["s1"])],
        "rule_field_0": "merchant",
        "rule_op_0": "contains",
        "rule_value_0": "qwerty",
    }
    p = await client.post("/review/preview", data=form)
    assert "sprzedawca / odbiorca zawiera „qwerty” i wydatek" in p.text
    assert "w innych grupach: 2 tr. (1)" in p.text and "Qwerty" in p.text
    r = await client.post("/review/assign", data=form)
    assert "zapisano" in r.text and "w innych grupach: 2 tr. (1)" in r.text
    assert "odśwież listę" in r.text
    [rule] = rules.all_rules(conn)
    assert rule.conditions.text[0] == rules.TextCondition("merchant", "contains", "qwerty")
    assert rule.conditions.direction == "out"
    for k in ("s1", "q1", "q2"):
        assert cat(conn, ids[k])[:2] == ("restauracje", "rule")
    status = dict(conn.execute("SELECT merchant, status FROM suggestion").fetchall())
    assert status == {"Qwerty": "accepted", "Qwerty-Sklep": "rejected"}


async def test_rule_text_starts_with(client: httpx.AsyncClient, service: Service) -> None:
    ids = _chain(service.conn)
    conn = service.conn
    form = {
        **_group("merchant", "Qwerty-Sklep"),
        "category_id": str(sid(conn, "spozywcze")),
        "txn": [str(ids["s1"])],
        "rule_field_0": "merchant",
        "rule_op_0": "starts_with",
        "rule_value_0": "Qwerty-",
    }
    p = await client.post("/review/preview", data=form)
    assert "zaczyna się od „Qwerty-”" in p.text and "innych grupach" not in p.text
    await client.post("/review/assign", data=form)
    assert cat(conn, ids["s1"])[:2] == ("spozywcze", "rule") and cat(conn, ids["q1"])[0] is None


async def test_rule_text_errors(client: httpx.AsyncClient, service: Service) -> None:
    ids = _chain(service.conn)
    conn = service.conn
    base = {
        **_group("merchant", "Qwerty-Sklep"),
        "category_id": str(sid(conn, "restauracje")),
        "txn": [str(ids["s1"])],
    }
    bad = {**base, "rule_field_0": "merchant", "rule_op_0": "contains", "rule_value_0": "lidl"}
    p = await client.post("/review/preview", data=bad)
    assert "nie pasują do żadnej pozycji grupy „Qwerty-Sklep”" in p.text
    r = await client.post("/review/assign", data=bad)
    assert "nie pasują do żadnej pozycji" in r.text and 'name="rule_value_0" value="lidl"' in r.text
    short = {**base, "rule_field_0": "merchant", "rule_op_0": "contains", "rule_value_0": "q"}
    r = await client.post("/review/assign", data=short)
    assert "co najmniej 3 znaki" in r.text
    regex = {**base, "rule_field_0": "merchant", "rule_op_0": "regex", "rule_value_0": "qwe"}
    r = await client.post("/review/assign", data=regex)
    assert "Nieznane pole albo operator" in r.text
    assert rules.all_rules(conn) == [] and cat(conn, ids["s1"])[0] is None
    # „tylko te” — tekst reguły bez znaczenia, kategoria ręczna
    r = await client.post("/review/assign", data={**bad, "only": "on"})
    assert "zapisano" in r.text and cat(conn, ids["s1"])[1] == "manual"


# --- M4h/1: pełne warunki reguły w kolejce ----------------------------------------------------


def _mixed(conn: sqlite3.Connection) -> dict[str, int]:
    """`_seed` + drugi przelew do tej samej osoby z innym tytułem (mieszanka pod odbiorcą)."""
    ids = _seed(conn)
    ids["p_out2"] = add(conn, "-40.00", "transfer_out", "Składka klasowa IX", "JAN TESTOWSKI")
    engine.recategorize(conn)
    return ids


def _cond(field: str, op: str, value: str, i: int = 0) -> dict[str, str]:
    return {f"rule_field_{i}": field, f"rule_op_{i}": op, f"rule_value_{i}": value}


async def test_group_body_has_full_conditions(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)
    r = await client.get("/review/group", params=_group("merchant", "Qwerty"))
    assert 'name="rule_field_0"' in r.text and '<option value="merchant" selected' in r.text
    assert 'name="rule_value_0" value="Qwerty"' in r.text
    assert "więcej warunków" in r.text
    for name in ("value_1", "value_2", "account_id", "kind", "amount_min", "amount_max", "rename"):
        assert f'name="rule_{name}"' in r.text, name
    assert '<option value="out" selected' in r.text  # kierunek grupy, do zmiany


async def test_rule_catches_part_of_group_rest_stays(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _mixed(service.conn)
    conn = service.conn
    leaf = sid(conn, "szkola-zajecia")
    _put_suggestion(conn, "Jan Testowski", sid(conn, "przelewy-rodzina"))
    form = {
        **_group("merchant", "Jan Testowski"),
        "category_id": str(leaf),
        "txn": [str(ids["p_out"]), str(ids["p_out2"])],
        "rule_direction": "out",
        **_cond("merchant", "equals", "Jan Testowski"),
        **_cond("description", "contains", "skladka", 1),
    }
    p = await client.post("/review/preview", data=form)
    assert "opis / tytuł zawiera „skladka”" in p.text
    assert "w tym 1 z 2 pozycji tej grupy" in p.text
    assert "Zostanie w kolejce 1" in p.text and "Prezent" in p.text
    r = await client.post("/review/assign", data=form)
    assert "zapisano" in r.text and 'id="m1r"' in r.text  # reszta grupy otwarta
    [rule] = rules.all_rules(conn)
    assert rule.conditions.text == (
        rules.TextCondition("merchant", "equals", "Jan Testowski"),
        rules.TextCondition("description", "contains", "skladka"),
    )
    assert cat(conn, ids["p_out2"])[:2] == ("szkola-zajecia", "rule")
    assert cat(conn, ids["p_out"])[0] is None
    # sprzedawca nie zamknięty w całości — podpowiedź AI czeka dalej
    assert conn.execute("SELECT status FROM suggestion").fetchone()[0] == "pending"


async def test_rule_amount_range_and_any_direction(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    form = {
        **_group("merchant", "Qwerty"),
        "category_id": str(sid(conn, "restauracje")),
        "txn": [str(ids["q1"]), str(ids["q2"])],
        **_cond("merchant", "equals", "Qwerty"),
        "rule_direction": "",
        "rule_amount_min": "25",
        "rule_rename": "Qwerty Bistro",
    }
    p = await client.post("/review/preview", data=form)
    assert "kwota ≥ 25" in p.text and "w tym 1 z 2 pozycji tej grupy" in p.text
    await client.post("/review/assign", data=form)
    [rule] = rules.all_rules(conn)
    assert rule.conditions.direction is None and rule.conditions.amount_min == Decimal("25.00")
    assert rule.rename == "Qwerty Bistro"
    assert cat(conn, ids["q1"])[:2] == ("restauracje", "rule") and cat(conn, ids["q2"])[0] is None


async def test_rule_without_merchant_condition(client: httpx.AsyncClient, service: Service) -> None:
    ids = _mixed(service.conn)
    conn = service.conn
    form = {
        **_group("merchant", "Jan Testowski"),
        "category_id": str(sid(conn, "prezenty")),
        "txn": [str(ids["p_out"]), str(ids["p_out2"])],
        "rule_direction": "out",
        **_cond("description", "starts_with", "prez"),
    }
    r = await client.post("/review/assign", data=form)
    assert "zapisano" in r.text
    [rule] = rules.all_rules(conn)
    assert rule.conditions.text == (rules.TextCondition("description", "starts_with", "prez"),)
    assert (
        cat(conn, ids["p_out"])[:2] == ("prezenty", "rule") and cat(conn, ids["p_out2"])[0] is None
    )


async def test_full_conditions_errors_keep_values(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    base = {
        **_group("merchant", "Qwerty"),
        "category_id": str(sid(conn, "restauracje")),
        "txn": [str(ids["q1"]), str(ids["q2"])],
        "rule_direction": "out",
        **_cond("merchant", "equals", "Qwerty"),
        **_cond("description", "contains", "xyz", 1),
    }
    r = await client.post("/review/assign", data={**base, "rule_amount_min": "100"})
    assert "nie pasują do żadnej pozycji" in r.text
    assert 'name="rule_value_1" value="xyz"' in r.text and 'value="100.00"' in r.text
    assert '<details class="rv-more" open>' in r.text  # dodatkowe warunki widoczne
    r = await client.post("/review/assign", data={**base, "rule_amount_max": "abc"})
    assert "Niepoprawna kwota" in r.text
    r = await client.post(
        "/review/assign", data={**base, **_cond("description", "contains", "x", 1)}
    )
    assert "co najmniej 3 znaki" in r.text
    assert rules.all_rules(conn) == []


async def test_ai_accept_defaults_to_merchant_equals(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    leaf = sid(conn, "restauracje")
    form = {**_group("merchant", "Qwerty"), "category_id": str(leaf), "all": "1"}
    r = await client.post("/review/assign", data=form)
    assert "zapisano" in r.text
    [rule] = rules.all_rules(conn)
    assert rule.conditions.text == (rules.TextCondition("merchant", "equals", "Qwerty"),)
    assert rule.conditions.direction == "out" and cat(conn, ids["q1"])[1] == "rule"
