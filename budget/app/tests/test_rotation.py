"""M32 E4: rekomendacja „dokąd przelać” po końcu promocji Velobanku."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from budget import inbox, promo_watch_velo, rotation, savings, summary
from budget.snapshot import Snapshot
from budget.storage import db

from .test_categorize_engine import conn
from .test_web import _client, service

__all__ = ["conn", "service"]

WAW = ZoneInfo("Europe/Warsaw")
OFFER = promo_watch_velo.Offer(
    "12/2026", 4.5, 1.0, 400_000, 5, ("card", "blik"), "karta i BLIK", date(2026, 11, 12), 92
)
ENDS = OFFER.ends_by()  # 2027-02-12
TODAY = date(2027, 2, 5)  # 7 dni do końca
VELO = 3


def watch(
    c: sqlite3.Connection, *, held: bool = False, offer: promo_watch_velo.Offer = OFFER
) -> None:
    db.kv_set(
        c,
        promo_watch_velo.KEY,
        {
            "offer": None if held else offer.to_json(),
            "checked": "2027-02-05T08:00:00",
            "held": held,
        },
    )


def velo_account(c: sqlite3.Connection, balance: str | None = "50000.00") -> None:
    c.execute(
        "INSERT INTO account (id, kind, currency, created_at, bank) "
        "VALUES (?, 'savings', 'PLN', '2026-01-01T00:00:00', 'VeloBank')",
        (VELO,),
    )
    if balance is not None:
        c.execute(
            "INSERT INTO balance_snapshot (account_id, balance_type, amount, currency, fetched_at) "
            "VALUES (?, 'ITAV', ?, 'PLN', '2027-02-05T06:00:00')",
            (VELO, balance),
        )


def target(
    c: sqlite3.Connection,
    base: str = "1",
    promo: str | None = "5.5",
    limit: str | None = "200000",
    until: str | None = "2027-05-31",
    name: str = "Konto X",
    number: str = "11112222333344445555666677",
) -> None:
    savings.save(
        c,
        account_id=None,
        name=name,
        account_number=number,
        opening_balance="0",
        opening_date="2027-01-01",
        base_rate=base,
        promo_rate=promo,
        promo_limit=limit,
        promo_until=until,
    )


@pytest.fixture
def setup(conn: sqlite3.Connection) -> sqlite3.Connection:
    watch(conn)
    velo_account(conn)
    target(conn)
    return conn


def test_recommends_transfer_seven_days_before_end(setup: sqlite3.Connection) -> None:
    rec = rotation.recommend(setup, TODAY)
    assert rec is not None
    horizon = (date(2027, 5, 31) - ENDS).days
    gross = Decimal(50000) * (Decimal("5.5") - Decimal(1)) / 100 / 365 * horizon
    assert rec.amount == Decimal("50000.00") and rec.account == "Konto X"
    assert rec.days_left == 7 and rec.ends_by == ENDS and rec.horizon == horizon
    assert rec.gain == savings.net(gross)
    assert "Przelej sam — Budżet nie przelewa" in rec.text and "Konto X" in rec.text


def test_held_edition_gives_none(setup: sqlite3.Connection) -> None:
    watch(setup, held=True)
    assert rotation.recommend(setup, TODAY) is None
    assert any(i.kind == "velo_held" for i in _alarm(setup))


def _alarm(c: sqlite3.Connection) -> list[inbox.Item]:
    now = datetime(2027, 2, 5, 8, tzinfo=WAW)
    return inbox.velo_promo_cards(c, inbox.Context(now, Snapshot(c)), inbox.BalanceMemo())


def test_no_state_gives_none(conn: sqlite3.Connection) -> None:
    velo_account(conn)
    target(conn)
    assert rotation.recommend(conn, TODAY) is None


def test_outside_window_gives_none(setup: sqlite3.Connection) -> None:
    assert rotation.recommend(setup, date(2027, 1, 28)) is None  # 15 dni
    assert rotation.recommend(setup, date(2027, 1, 29)) is not None  # 14 dni
    assert rotation.recommend(setup, ENDS) is not None  # ostatni dzień
    assert rotation.recommend(setup, date(2027, 2, 13)) is None  # po końcu


def test_gain_below_one_zloty_gives_none(conn: sqlite3.Connection) -> None:
    watch(conn)
    velo_account(conn, "10.00")  # 10 zł → grosze zysku
    target(conn)
    assert rotation.recommend(conn, TODAY) is None


def test_target_rate_not_above_velo_base_gives_none(conn: sqlite3.Connection) -> None:
    watch(conn)
    velo_account(conn)
    target(conn, base="1", promo="1", until="2027-05-31")
    assert rotation.recommend(conn, TODAY) is None


def test_expired_target_promo_uses_base_rate(conn: sqlite3.Connection) -> None:
    """Promocja konta docelowego kończy się przed końcem Velo: liczy się stopa bazowa, 30 dni."""
    watch(conn)
    velo_account(conn)
    target(conn, base="3", promo="6", until="2027-02-10")
    rec = rotation.recommend(conn, TODAY)
    assert rec is not None and rec.rate == Decimal(3) and rec.horizon == 30


def test_amount_capped_by_promo_limit(conn: sqlite3.Connection) -> None:
    watch(conn)
    velo_account(conn, "50000.00")
    target(conn, limit="20000")
    rec = rotation.recommend(conn, TODAY)
    assert rec is not None and rec.amount == Decimal("20000.00")


def test_no_balance_or_no_target_gives_none(conn: sqlite3.Connection) -> None:
    watch(conn)
    velo_account(conn, None)
    target(conn)
    assert rotation.recommend(conn, TODAY) is None
    conn.execute("UPDATE savings_account SET archived_at = '2027-01-02'")
    assert rotation.recommend(conn, TODAY) is None


def test_picks_best_gain(setup: sqlite3.Connection) -> None:
    target(setup, base="1", promo="3", name="Konto Y", number="99998888777766665555444433")
    rec = rotation.recommend(setup, TODAY)
    assert rec is not None and rec.account == "Konto X"


def test_other_banks_do_not_count(conn: sqlite3.Connection) -> None:
    watch(conn)
    conn.execute("UPDATE account SET bank = 'Bank A' WHERE id = 1")
    conn.execute(
        "INSERT INTO balance_snapshot (account_id, balance_type, amount, currency, fetched_at) "
        "VALUES (1, 'ITAV', '90000.00', 'PLN', '2027-02-05T06:00:00')"
    )
    target(conn)
    assert rotation.recommend(conn, TODAY) is None


def test_velo_current_account_is_not_counted(setup: sqlite3.Connection) -> None:
    """ROR z wpływami nie jest „środkami do przelania” — liczy się tylko konto oszczędnościowe."""
    setup.execute(
        "INSERT INTO account (id, kind, currency, created_at, bank) "
        "VALUES (9, 'current', 'PLN', '2026-01-01T00:00:00', 'VeloBank')"
    )
    setup.execute(
        "INSERT INTO balance_snapshot (account_id, balance_type, amount, currency, fetched_at) "
        "VALUES (9, 'ITAV', '30000.00', 'PLN', '2027-02-05T06:00:00')"
    )
    rec = rotation.recommend(setup, TODAY)
    assert rec is not None and rec.amount == Decimal("50000.00")


# --- dzwonek i powiadomienia -----------------------------------------------------------------


def test_bell_card(setup: sqlite3.Connection) -> None:
    now = datetime(2027, 2, 5, 8, tzinfo=WAW)
    cards = [
        i for i in inbox.items(Snapshot(setup), now, inbox.BalanceMemo()) if i.kind == "rotation"
    ]
    assert len(cards) == 1
    assert "Konto X" in cards[0].title and "Przelej sam" in cards[0].detail
    assert cards[0].severity == "warn"


def test_bell_silent_when_held(setup: sqlite3.Connection) -> None:
    watch(setup, held=True)
    now = datetime(2027, 2, 5, 8, tzinfo=WAW)
    assert not [
        i for i in inbox.items(Snapshot(setup), now, inbox.BalanceMemo()) if i.kind == "rotation"
    ]


@pytest.mark.parametrize(
    ("day", "sent"), [(14, True), (7, True), (2, True), (5, False), (0, False)]
)
def test_messages_on_thresholds(setup: sqlite3.Connection, day: int, sent: bool) -> None:
    today = ENDS - timedelta(days=day)
    msgs = summary.rotation_messages(setup, today)
    assert bool(msgs) is sent
    if sent:
        assert msgs[0].kind == "rotation" and msgs[0].period == f"{ENDS:%Y-%m-%d}-{day}"
        assert "Przelej sam" in msgs[0].text


def test_messages_none_when_held(setup: sqlite3.Connection) -> None:
    watch(setup, held=True)
    assert summary.rotation_messages(setup, TODAY) == []


# --- panel -----------------------------------------------------------------------------------


async def test_promo_card_section(service) -> None:  # type: ignore[no-untyped-def]
    conn = service.conn
    watch(conn)
    velo_account(conn)
    target(conn)
    service.now = lambda: datetime(2027, 2, 5, 8, tzinfo=WAW)
    async with _client(service) as client:
        page = (await client.get("/invest")).text
    assert "Dokąd przelać" in page and "Konto X" in page and "Przelej sam" in page
