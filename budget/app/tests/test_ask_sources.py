"""Czat M12 E3b: rejestr źródeł danych — wartości jak na ekranie, do LLM bez nazw."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from budget import card, flex, forecast, loan
from budget.ask import sources
from budget.categorize import engine
from budget.money import pl
from budget.snapshot import Snapshot

from .test_card import CARD, buy
from .test_categorize_engine import add, conn, sid
from .test_flex import serie
from .test_forecast import at, seeded
from .test_loan import make as make_loan
from .test_piggy import make as make_piggy
from .test_savings import NUMBER
from .test_savings import make as make_savings

__all__ = ["conn"]

TODAY = date(2026, 10, 3)


def ctx(c: sqlite3.Connection, now: datetime) -> sources.Ctx:
    return sources.Ctx(c, Snapshot(c), TODAY, now, date(2026, 10, 1))


def test_registry_names_are_unique_and_described() -> None:
    names = [s.name for s in sources.REGISTRY]
    assert len(names) == len(set(names)) and "transactions" not in names
    assert all(s.description and s.label for s in sources.REGISTRY)
    assert tuple(names) == sources.NAMES


def test_payday_matches_forecast(conn: sqlite3.Connection) -> None:
    seeded(conn)
    now = at(3)
    fc = forecast.for_today(Snapshot(conn), TODAY, now)
    assert fc is not None
    res = sources.run("payday", ctx(conn, now))
    facts = {f.label: f.value for f in res.facts}
    assert facts["Wolne środki dziś"].startswith("4")  # 5000 − dług karty 400 = 4 600
    assert res.link == "/"
    assert res.filters  # „jak policzono”
    assert "Wolne środki dziś" in str(res.for_llm())


def test_payday_without_balance_has_note(conn: sqlite3.Connection) -> None:
    res = sources.run("payday", ctx(conn, at(3)))
    assert not res.facts and "salda" in res.note.lower()


def test_unknown_source_is_rejected(conn: sqlite3.Connection) -> None:
    try:
        sources.run("nie_ma", ctx(conn, at(3)))
    except sources.SourceError as exc:
        assert "nie_ma" in str(exc)
    else:
        raise AssertionError("brak błędu")


def test_for_llm_replaces_private_names() -> None:
    res = sources.SourceResult(
        source="x",
        facts=[sources.Fact("Konto A", "10,00 zł", llm_label="[K1]")],
        filters=["jak policzono"],
        link="/",
    )
    assert "Konto A" not in str(res.for_llm()) and res.labels == {"[K1]": "Konto A"}


def test_month_parsing_defaults_to_current() -> None:
    assert sources.month_of("", date(2026, 10, 3)) == date(2026, 10, 1)
    assert sources.month_of("2026-08", date(2026, 10, 3)) == date(2026, 8, 1)
    assert sources.month_of("zły", date(2026, 10, 3)) == date(2026, 10, 1)


def facts(res: sources.SourceResult) -> dict[str, str]:
    return {f.label: f.value for f in res.facts}


def test_card_shared_counter_and_due(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-10-10", 3)
    res = sources.run("card", ctx(conn, at(20)))
    got = facts(res)
    assert got["Płatności kartą w miesiącu"] == "3 z 5 (brakuje 2)"
    assert res.link == "/card" and res.filters and not res.note


def test_card_per_person_is_redacted_for_llm(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-10-10", 2)
    holder = card.add_holder(conn, "Osoba Testowa")
    for (txn_id,) in conn.execute("SELECT id FROM txn WHERE account_id = ?", (CARD,)).fetchall():
        card.assign(conn, txn_id, holder)
    res = sources.run("card", ctx(conn, at(20)))
    assert facts(res)["Osoba Testowa"].startswith("2 z 5")
    assert "Testowa" not in str(res.for_llm()) and res.labels == {"[Osoba 1]": "Osoba Testowa"}


def test_card_past_month_has_no_due_part(conn: sqlite3.Connection) -> None:
    buy(conn, "2026-09-10", 4)
    got = facts(sources.run("card", ctx(conn, at(20)), "2026-09"))
    assert got["Płatności kartą w miesiącu"] == "4 z 5 (brakuje 1)"
    assert "Do spłaty w terminie" not in got


def test_budget_matches_flex_screen(conn: sqlite3.Connection) -> None:
    flex.set_budget(conn, date(2026, 10, 1), Decimal("1000"))
    f = flex.build(Snapshot(conn), date(2026, 10, 1), TODAY)
    got = facts(sources.run("budget", ctx(conn, at(3))))
    assert f.remaining is not None
    assert got["Zostało w budżecie elastycznym"] == pl(f.remaining, "PLN")
    assert got["Budżet elastyczny"] == pl(Decimal("1000"), "PLN")


def test_budget_facts_count_non_monthly_against_the_pool(conn: sqlite3.Connection) -> None:
    flex.set_budget(conn, date(2026, 10, 1), Decimal("1000"))
    add(conn, "-100.00", "card", "LIDL XYZ POL", day="2026-10-02")
    once = add(conn, "-300.00", "card", "ELEKTRO RTV", day="2026-10-02")
    engine.recategorize(conn)
    engine.set_manual(conn, once, sid(conn, "elektronika"))
    got = facts(sources.run("budget", ctx(conn, at(3))))
    assert got["Wydane elastyczne"] == pl(Decimal("100"), "PLN")
    assert got["Wydatki nieregularne (obciążają pulę)"] == pl(Decimal("300"), "PLN")
    assert got["Obciążenie puli (elastyczne + nieregularne)"] == pl(Decimal("400"), "PLN")
    assert got["Zostało w budżecie elastycznym"] == pl(Decimal("600"), "PLN")
    assert "Wydatki nieregularne (informacyjnie)" not in got


def test_budget_without_amount_says_so(conn: sqlite3.Connection) -> None:
    got = facts(sources.run("budget", ctx(conn, at(3))))
    assert got["Budżet elastyczny"] == "nie ustawiono"


def test_budget_month_param_and_link(conn: sqlite3.Connection) -> None:
    res = sources.run("budget", ctx(conn, at(3)), "2026-08")
    assert res.link == "/budget?month=2026-08" and "sierpień" in facts(res)["Miesiąc"].lower()


def test_recurring_lists_series_and_redacts_names(conn: sqlite3.Connection) -> None:
    serie(conn, "abc", "120.00")
    res = sources.run("recurring", ctx(conn, at(3)))
    got = facts(res)
    assert "Seria abc" in got and "120" in got["Seria abc"] and "oczekiwane" in got["Seria abc"]
    assert "abc" not in str(res.for_llm()) and res.labels == {"[Seria 1]": "Seria abc"}
    assert res.link == "/recurring"
    assert sources.run("recurring", ctx(conn, at(3)), "2026-09").link == "/recurring?month=2026-09"


def test_savings_balances_and_piggies_redacted(conn: sqlite3.Connection) -> None:
    make_savings(conn)
    make_piggy(conn)
    res = sources.run("savings", ctx(conn, at(3)))
    got = facts(res)
    assert got["Oszczędnościowe"].startswith("1")  # saldo z odsetkami ≥ 1000
    assert "Wakacje" in got and "Oszczędnościowe" not in str(res.for_llm())
    assert "Wakacje" not in str(res.for_llm()) and NUMBER not in str(res)
    assert res.labels["[Konto 1]"] == "Oszczędnościowe" and res.labels["[Skarbonka 1]"] == "Wakacje"


def test_savings_empty_has_note(conn: sqlite3.Connection) -> None:
    assert "Brak" in sources.run("savings", ctx(conn, at(3))).note


def test_loan_matches_summary_and_redacts_name(conn: sqlite3.Connection) -> None:
    lid = make_loan(conn)
    lo = loan.get(conn, lid)
    s = loan.summary(lo, loan.schedule(lo), TODAY)
    res = sources.run("loan", ctx(conn, at(3)))
    got = facts(res)
    assert got["Dom"].startswith(pl(s.principal, "PLN")) or pl(s.principal, "PLN") in got["Dom"]
    assert pl(s.installment, "PLN") in got["Dom"]
    assert "Dom" not in str(res.for_llm()) and res.labels == {"[Kredyt 1]": "Dom"}
    assert res.link == "/loan"


def test_loan_empty_has_note(conn: sqlite3.Connection) -> None:
    assert "Brak" in sources.run("loan", ctx(conn, at(3))).note
