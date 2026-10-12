"""Panel M4a: Wydatki, kategorie w Transakcjach, Reguły (edytor + podgląd), Słownik, Kategorie."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import httpx
import pytest

from budget import __version__, split
from budget.categorize import engine, rules, taxonomy
from budget.service import Service
from budget.storage.db import now_iso

from .test_categorize_engine import add
from .test_web import INGRESS, _client

__all__ = ["service"]
from .test_web import service

TODAY = date.today()
DAY = TODAY.replace(day=1).isoformat()


def _seed(conn: sqlite3.Connection) -> dict[str, int]:
    conn.execute(
        "INSERT INTO account (id, kind, currency, display_name, created_at) "
        "VALUES (1, 'current', 'PLN', 'Rachunek', ?)",
        (now_iso(),),
    )
    ids = {
        "lidl": add(conn, "-50.00", "card", "LIDL UL. X XYZ POL", day=DAY),
        "kebab": add(conn, "-30.00", "card", "KEBAB ABC XYZ POL", day=DAY),
        "orlen": add(conn, "-200.00", "card", "ORLEN STACJA 1 XYZ", day=DAY),
        "salary": add(conn, "5000.00", "transfer_in", "Pensja", "FIRMA SP Z O O", day=DAY),
        "own": add(conn, "-700.00", "card_repayment", "", None, day=DAY, transfer_group="t1"),
    }
    engine.recategorize(conn)
    return ids


@pytest.fixture
async def client(service: Service) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(service) as c:
        yield c


async def test_nav_and_empty_pages(client: httpx.AsyncClient) -> None:
    for path in ("/spending", "/rules", "/rules/new", "/dictionary", "/categories"):
        r = await client.get(path)
        assert r.status_code == 200, path
        assert r.headers["cache-control"] == "no-store"
    page = (await client.get("/")).text
    assert f'href="{INGRESS}/spending"' in page and f'href="{INGRESS}/rules"' in page
    assert "brak wydatków" in (await client.get("/spending")).text
    rules_page = (await client.get("/rules")).text
    assert "Zawsze dla" not in rules_page and "utwórz regułę" in rules_page


async def test_spending_page(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)
    page = (await client.get("/spending")).text
    assert "Jedzenie" in page and "Transport" in page
    assert "Nieskategoryzowane" not in page  # wszystkie wydatki mają kategorię ze słownika
    assert "280,00" in page  # 50 + 30 + 200
    assert "przypisz kategorie" not in page
    assert f"{INGRESS}/transactions?category=2&date_from={DAY}" in page
    assert "bez kategorii" in page  # pensja bez reguły
    # przyszły miesiąc → bieżący; brak strzałki „dalej”
    future = (await client.get("/spending?month=2999-01")).text
    assert 'aria-label="następny miesiąc"' not in future


async def test_transactions_filters_and_manual_category(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _seed(service.conn)
    page = (await client.get("/transactions?category=none")).text
    assert "Firma Sp Z O O" in page and "Lidl" not in page
    assert "przelew własny" not in page  # przelew wewnętrzny nie jest „bez kategorii”
    food = taxonomy.by_slug(service.conn)["jedzenie"].id
    page = (await client.get(f"/transactions?category={food}&direction=out")).text
    assert "Lidl" in page and "Firma" not in page

    form = (await client.get(f"/transactions/{ids['kebab']}/category")).text
    assert "<select" in form and "automatycznie" in form
    assert 'name="make_rule"' in form and 'name="make_rule" value="1" checked' not in form
    leaf = taxonomy.by_slug(service.conn)["restauracje"].id
    r = await client.post(f"/transactions/{ids['kebab']}/category", data={"category_id": str(leaf)})
    assert r.status_code == 200
    assert "Restauracje i kawiarnie" in r.text and "ręczna" in r.text
    assert "/rules/new" not in r.text and "Zawsze dla" not in r.text
    assert rules.all_rules(service.conn) == []  # domyślnie bez reguły
    r = await client.post(f"/transactions/{ids['kebab']}/category", data={"category_id": ""})
    assert "ręczna" not in r.text
    r = await client.post(f"/transactions/{ids['own']}/category", data={"category_id": str(leaf)})
    assert "przelew własny" in r.text


async def test_rule_preview_save_and_actions(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    salary = taxonomy.by_slug(conn)["wynagrodzenie"].id
    form = {
        "field_0": "merchant",
        "op_0": "contains",
        "value_0": "firma",
        "category_id": str(salary),
        "direction": "in",
    }
    r = await client.post("/rules/preview", data=form)
    assert "Pasuje: 1" in r.text and "Firma Sp Z O O" in r.text
    r = await client.post("/rules/preview", data={**form, "value_0": ""})
    assert "co najmniej jednego" in r.text

    r = await client.post("/rules/save", data={**form, "rename": "Pensja"})
    assert r.status_code == 303 and r.headers["location"] == f"{INGRESS}/rules"
    page = (await client.get("/rules")).text
    assert "Reguła zapisana; zaktualizowane transakcje: 1" in page
    assert "sprzedawca / odbiorca zawiera „firma”" in page
    assert (
        conn.execute("SELECT merchant FROM txn WHERE id = ?", (ids["salary"],)).fetchone()[0]
        == "Pensja"
    )

    rid = rules.all_rules(conn)[0].id
    assert (await client.get(f"/rules/{rid}")).status_code == 200
    await client.post(f"/rules/{rid}/toggle")
    assert (
        conn.execute("SELECT category_id FROM txn WHERE id = ?", (ids["salary"],)).fetchone()[0]
        is None
    )
    await client.post(f"/rules/{rid}/move", data={"step": "-1"})
    await client.post(f"/rules/{rid}/delete")
    assert rules.all_rules(conn) == []
    r = await client.get("/rules/999")
    assert r.status_code == 303


async def test_rule_save_invalid_keeps_form(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)
    r = await client.post(
        "/rules/save", data={"field_0": "merchant", "op_0": "contains", "value_0": "x"}
    )
    assert r.status_code == 200 and "Wybierz podkategorię" in r.text
    r = await client.post(
        "/rules/save",
        data={"value_0": "x", "category_id": "110", "amount_min": "abc"},
    )
    assert "Niepoprawna kwota" in r.text


async def test_new_rule_prefilled_from_transaction(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _seed(service.conn)
    page = (await client.get(f"/rules/new?txn={ids['lidl']}")).text
    assert 'value="Lidl"' in page
    assert '<option value="equals" selected>' in page


async def test_dictionary_and_categories(client: httpx.AsyncClient, service: Service) -> None:
    _seed(service.conn)
    page = (await client.get("/dictionary?q=lidl")).text
    assert "Lidl" in page and "Biedronka" not in page
    page = (await client.get("/dictionary")).text
    assert "(słowa ogólne)" in page
    assert f"v{__version__}" in page  # wersja słownika nie przesłania wersji add-onu

    r = await client.post("/categories/add", data={"parent_id": "4", "name": "Rower"})
    assert r.status_code == 303
    assert "Dodano podkategorię" in (await client.get("/categories")).text
    r = await client.post("/categories/add", data={"parent_id": "4", "name": "rower"})
    assert "już istnieje" in (await client.get("/categories")).text
    await client.post("/categories/110/rename", data={"name": "Zakupy spożywcze"})
    assert "Zakupy spożywcze" in (await client.get("/categories")).text


async def test_categories_leaf_row_collapses_edit_forms(
    client: httpx.AsyncClient, service: Service
) -> None:
    _seed(service.conn)
    page = (await client.get("/categories")).text
    rows = page.split('<details class="leaf">')[1:]
    leaves = service.conn.execute(
        "SELECT COUNT(*) FROM category WHERE parent_id IS NOT NULL"
    ).fetchone()[0]
    assert len(rows) == leaves
    row = next(r for r in rows if "Restauracje i kawiarnie</span>" in r).split("</details>")[0]
    summary, forms = row.split("</summary>")
    assert "elastyczne · 1 tr." in summary
    for action in ("rename", "group", "move"):
        assert f'action="{INGRESS}/categories/111/{action}"' in forms


async def test_categories_add_main_move_delete(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    r = await client.post("/categories/add-main", data={"name": "Wyjazdy"})
    assert r.status_code == 303
    page = (await client.get("/categories")).text
    assert "Dodano kategorię główną" in page and 'value="Wyjazdy"' in page
    trips = taxonomy.by_slug(conn)["wyjazdy"].id
    assert f'action="{INGRESS}/categories/{trips}/delete"' in page  # pusta → można usunąć
    assert f'action="{INGRESS}/categories/2/delete"' not in page

    before = conn.execute("SELECT category_id FROM txn WHERE id = ?", (ids["kebab"],)).fetchone()
    r = await client.post("/categories/111/move", data={"parent_id": str(trips)})
    assert r.status_code == 303
    page = (await client.get("/categories")).text
    assert "Przeniesiono „Restauracje i kawiarnie” do „Wyjazdy”" in page
    assert f'action="{INGRESS}/categories/{trips}/delete"' not in page
    after = conn.execute("SELECT category_id FROM txn WHERE id = ?", (ids["kebab"],)).fetchone()
    assert before[0] == after[0]
    assert "Wyjazdy" in (await client.get("/spending")).text

    await client.post("/categories/111/move", data={"parent_id": str(trips)})
    assert "już jest" in (await client.get("/categories")).text
    await client.post("/categories/111/move", data={"parent_id": "2"})
    r = await client.post(f"/categories/{trips}/delete")
    assert r.status_code == 303
    assert "Usunięto kategorię „Wyjazdy”" in (await client.get("/categories")).text
    await client.post("/categories/2/delete")
    assert "najpierw je przenieś" in (await client.get("/categories")).text


async def test_rule_from_correction_takes_over_manual(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    gifts = taxonomy.by_slug(conn)["prezenty"].id
    await client.post(f"/transactions/{ids['salary']}/category", data={"category_id": str(gifts)})
    page = (await client.get(f"/rules/new?txn={ids['salary']}")).text
    assert f'name="txn" value="{ids["salary"]}"' in page
    form = {
        "field_0": "merchant",
        "op_0": "equals",
        "value_0": "Firma Sp Z O O",
        "category_id": str(gifts),
        "txn": str(ids["salary"]),
    }
    r = await client.post("/rules/preview", data=form)
    assert "Dostanie tę kategorię: <strong>1</strong>" in r.text and "Ręcznie" not in r.text
    await client.post("/rules/save", data=form)
    row = conn.execute("SELECT category_source FROM txn WHERE id = ?", (ids["salary"],)).fetchone()
    assert row[0] == "rule"


# --- M4h/2: reguła z Transakcji w miejscu -------------------------------------------------------


def _txn_rule(cid: int, value: str, **extra: str) -> dict[str, str]:
    return {
        "category_id": str(cid),
        "make_rule": "1",
        "rule_field_0": "merchant",
        "rule_op_0": "equals",
        "rule_value_0": value,
        "rule_direction": "in",
        **extra,
    }


async def test_txn_category_form_prefills_rule(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    form = (await client.get(f"/transactions/{ids['salary']}/category")).text
    assert 'name="rule_value_0" value="Firma Sp Z O O"' in form
    assert '<option value="in" selected' in form  # kierunek ze znaku kwoty
    assert "rule-preview" in form


async def test_txn_rule_preview_and_save(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    salary = taxonomy.by_slug(conn)["wynagrodzenie"].id
    other = add(conn, "5100.00", "transfer_in", "Pensja X", "FIRMA SP Z O O", day=DAY)
    engine.recategorize(conn)
    data = _txn_rule(salary, "Firma Sp Z O O", rule_value_1="pensja", rule_field_1="description")
    p = await client.post(f"/transactions/{ids['salary']}/rule-preview", data=data)
    assert "opis / tytuł zawiera „pensja”" in p.text and "Pasuje 2" in p.text
    r = await client.post(f"/transactions/{ids['salary']}/category", data=data)
    assert "Wynagrodzenie" in r.text and "reguła" in r.text
    [rule] = rules.all_rules(conn)
    assert rule.conditions.direction == "in" and len(rule.conditions.text) == 2
    for t in (ids["salary"], other):
        row = conn.execute("SELECT category_source FROM txn WHERE id = ?", (t,)).fetchone()
        assert row[0] == "rule"


async def test_txn_rule_replaces_manual_category(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    gifts = taxonomy.by_slug(conn)["prezenty"].id
    salary = taxonomy.by_slug(conn)["wynagrodzenie"].id
    await client.post(f"/transactions/{ids['salary']}/category", data={"category_id": str(gifts)})
    await client.post(
        f"/transactions/{ids['salary']}/category", data=_txn_rule(salary, "Firma Sp Z O O")
    )
    row = conn.execute(
        "SELECT category_source, category_id FROM txn WHERE id = ?", (ids["salary"],)
    ).fetchone()
    assert tuple(row) == ("rule", salary)


async def test_txn_rule_errors(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    conn = service.conn
    salary = taxonomy.by_slug(conn)["wynagrodzenie"].id
    bad = _txn_rule(salary, "Lidl")
    p = await client.post(f"/transactions/{ids['salary']}/rule-preview", data=bad)
    assert "nie pasują do tej transakcji" in p.text
    r = await client.post(f"/transactions/{ids['salary']}/category", data=bad)
    assert "nie pasują do tej transakcji" in r.text
    assert 'name="make_rule" value="1" checked' in r.text and 'value="Lidl"' in r.text
    r = await client.post(
        f"/transactions/{ids['salary']}/category", data={**bad, "category_id": ""}
    )
    assert "Wybierz podkategorię" in r.text
    assert rules.all_rules(conn) == []
    row = conn.execute("SELECT category_id FROM txn WHERE id = ?", (ids["salary"],)).fetchone()
    assert row[0] is None


async def test_transactions_category_filter_matches_split_parts(
    client: httpx.AsyncClient, service: Service
) -> None:
    ids = _seed(service.conn)
    drogeria = taxonomy.by_slug(service.conn)["drogeria"].id
    spozywcze = taxonomy.by_slug(service.conn)["spozywcze"].id
    split.save(service.conn, ids["lidl"], [(drogeria, Decimal("-10")), (spozywcze, Decimal("-40"))])
    for category in (drogeria, 5):  # podkategoria części i jej kategoria główna (Zdrowie i uroda)
        page = (await client.get(f"/transactions?category={category}")).text
        assert "LIDL UL. X" in page and "KEBAB" not in page, category


async def test_split_form_save_and_clear(client: httpx.AsyncClient, service: Service) -> None:
    conn = service.conn
    ids = _seed(conn)
    drogeria = taxonomy.by_slug(conn)["drogeria"].id
    spozywcze = taxonomy.by_slug(conn)["spozywcze"].id
    url = f"/transactions/{ids['lidl']}/split"

    editor = (await client.get(f"/transactions/{ids['lidl']}/category")).text
    assert f'hx-get="{INGRESS}{url}"' in editor and "Podziel na kategorie" in editor
    form = (await client.get(url)).text
    assert 'data-total="5000"' in form and "Zostało do przydzielenia" in form
    assert form.count('name="amount"') == 2 and "Usuń podział" not in form

    # kwoty bez znaku, z przecinkiem; pusty wiersz pomijany; reszta ≠ 0 → błąd i wiersze zostają
    bad = {"category_id": [str(drogeria), str(spozywcze), ""], "amount": ["12,50", "30", ""]}
    r = await client.post(url, data=bad)
    assert "Zostało do przydzielenia: 7,50" in r.text and 'value="12,50"' in r.text
    assert split.get(conn, ids["lidl"]) == []

    r = await client.post(
        url, data={"category_id": [str(drogeria), str(spozywcze)], "amount": ["12,50", "37.50"]}
    )
    assert split.get(conn, ids["lidl"]) == [
        (drogeria, Decimal("-12.50")),
        (spozywcze, Decimal("-37.50")),
    ]
    assert "2 kategorie" in r.text and "Drogeria" in r.text and "12,50" in r.text

    # lista: znacznik i części w podpisie; edytor podzielonej transakcji = formularz podziału
    page = (await client.get("/transactions")).text
    assert "2 kategorie" in page and "Spożywcze" in page
    again = (await client.get(f"/transactions/{ids['lidl']}/category")).text
    assert "Usuń podział" in again and 'value="12,50"' in again

    r = await client.post(url, data={"action": "clear"})
    assert split.get(conn, ids["lidl"]) == [] and "2 kategorie" not in r.text
    row = conn.execute("SELECT category_source FROM txn WHERE id = ?", (ids["lidl"],)).fetchone()
    assert row[0] != "manual"


async def test_split_rejects_own_transfer(client: httpx.AsyncClient, service: Service) -> None:
    ids = _seed(service.conn)
    leaf = taxonomy.by_slug(service.conn)["drogeria"].id
    r = await client.post(
        f"/transactions/{ids['own']}/split",
        data={"category_id": [str(leaf), str(leaf)], "amount": ["300", "400"]},
    )
    assert "własnymi kontami" in r.text and split.get(service.conn, ids["own"]) == []


async def test_lidl_receipt_link_choice_and_category_map(
    client: httpx.AsyncClient, service: Service
) -> None:
    import json

    from budget import lidl_link

    conn = service.conn
    ids = _seed(conn)  # LIDL −50,00
    twin = add(conn, "-50.00", "card", "LIDL UL. X XYZ POL", day=DAY)
    path = service.settings.lidl_receipts_path
    path.parent.mkdir(parents=True)
    receipt = {"id": "p1", "day": DAY, "paid": 50.0, "url_path": "/paragony/p1",
               "parts": {"food": 30.0, "drugstore": 20.0}}  # fmt: skip
    path.write_text(json.dumps({"version": 1, "receipts": [receipt]}), encoding="utf-8")
    assert service.link_lidl() == lidl_link.MatchResult(0, 1, 0)  # dwie płatności — do wyboru

    editor = (await client.get(f"/transactions/{ids['lidl']}/category")).text
    assert "Paragon Lidl pasuje do kilku płatności" in editor and '"ticket_id": "p1"' in editor
    r = await client.post(f"/transactions/{ids['lidl']}/lidl", data={"ticket_id": "p1"})
    assert "2 kategorie" in r.text and "/app/f0987e0f_lidl/paragony/p1" in r.text
    assert lidl_link.links(conn) == {ids["lidl"]: ("p1", "chosen")}
    assert "Paragon Lidl pasuje" not in (await client.get(f"/transactions/{twin}/category")).text
    page = (await client.get("/transactions")).text
    assert 'target="_top">paragon Lidl</a>' in page

    cats = (await client.get("/categories")).text
    assert 'action="' + INGRESS + '/categories/lidl"' in cats
    m = lidl_link.category_map(conn)
    r = await client.post(
        "/categories/lidl", data={**{k: str(v) for k, v in m.items()}, "kids": "abc"}
    )
    assert r.status_code == 303 and lidl_link.category_map(conn) == m
    new = {**m, "kids": taxonomy.by_slug(conn)["drogeria"].id}
    await client.post("/categories/lidl", data={k: str(v) for k, v in new.items()})
    assert lidl_link.category_map(conn) == new
