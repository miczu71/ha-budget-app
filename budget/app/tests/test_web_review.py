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
