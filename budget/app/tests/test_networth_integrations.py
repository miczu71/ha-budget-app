"""Majątek netto (M26 E4): encja MQTT, podsumowanie miesięczne, źródło czatu, agent M22."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from budget import ha_publisher, invest, invest_why, networth, summary
from budget.ask import sources
from budget.snapshot import Snapshot

from .test_categorize_engine import conn
from .test_invest_alerts import advice
from .test_loan import make as make_loan
from .test_networth import balance

__all__ = ["conn"]

TODAY = date(2026, 10, 20)
NOW = datetime(2026, 10, 20, 8, 0, tzinfo=ZoneInfo("Europe/Warsaw"))


def seed(c: sqlite3.Connection) -> None:
    balance(c, 1, "ITAV", "20000.00")
    make_loan(c, principal="100000", principal_date="2026-10-20", last_payment_date="2046-10-20")
    old = invest.save_asset(c, None, "bonds", "Tajne obligacje", "5000", "", "", "", False)
    c.execute("UPDATE invest_asset SET valued_at = '2026-06-01' WHERE id = ?", (old,))
    c.execute(
        "INSERT INTO networth_snapshot (day, total, assets, liabilities, components_json, approx) "
        "VALUES ('2026-09-18', '-80000', '20000', '100000', '[]', 0)"
    )


def test_sensor_state_and_attributes(conn: sqlite3.Connection) -> None:
    seed(conn)
    ents = {e.key: e for e in ha_publisher.build_entities(Snapshot(conn), now=NOW, today=TODAY)}
    e = ents["net_worth"]
    assert e.state == "-75000.00"
    assert e.attributes["assets"] == "25000.00" and e.attributes["liabilities"] == "100000.00"
    assert e.attributes["ltv"] == 400.0 and e.attributes["liquidity_months"] is None
    assert e.attributes["change_mom"] == "5000.00" and e.attributes["change_yoy"] is None
    assert e.attributes["stale"] == ["Tajne obligacje"]


def test_no_sensor_without_components(conn: sqlite3.Connection) -> None:
    ents = ha_publisher.build_entities(Snapshot(conn), now=NOW, today=TODAY)
    assert "net_worth" not in {e.key for e in ents}


def test_monthly_has_net_worth_line_and_stale_reminder(conn: sqlite3.Connection) -> None:
    seed(conn)
    lines = summary.monthly(Snapshot(conn), TODAY).text.splitlines()
    nbsp = " "
    assert f"Majątek netto: −75{nbsp}000{nbsp}zł (+5{nbsp}000{nbsp}zł m/m)" in lines
    assert any(ln.startswith("Zaktualizuj wartość: Tajne obligacje") for ln in lines)


def test_chat_source_has_totals_and_no_names(conn: sqlite3.Connection) -> None:
    seed(conn)
    res = sources.run("majatek", sources.Ctx(conn, Snapshot(conn), TODAY, NOW, TODAY))
    facts = {f.label: f.value for f in res.facts}
    assert facts["Aktywa"].startswith("25") and "Zmiana m/m" in facts
    assert res.link == "/networth" and res.filters
    assert "Tajne" not in str(res.for_llm())


def test_chat_source_empty(conn: sqlite3.Connection) -> None:
    res = sources.run("majatek", sources.Ctx(conn, Snapshot(conn), TODAY, NOW, TODAY))
    assert res.note and not res.facts


def test_why_facts_have_coarse_liquidity_and_ltv() -> None:
    nw = networth.NetWorth(
        TODAY,
        (
            networth.Component(networth.ACCOUNTS, "A", Decimal(20000)),
            networth.Component(networth.LOANS, "K", Decimal(7000), liability=True),
        ),
        spend=Decimal(3000),
    )
    data = invest_why.facts(advice(), nw)
    assert data is not None
    assert data["plynnosc_miesiecy_wydatkow"] == 6 and data["kredyty_do_aktywow_proc"] == 35
    assert "plynnosc_miesiecy_wydatkow" not in (invest_why.facts(advice()) or {})
