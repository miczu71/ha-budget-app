"""M32 E2: licznik transakcji bezgotówkowych (karta, BLIK) edycji promocji i jego powiadomienia."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from budget import inbox, promo_track, summary
from budget.service import Service
from budget.snapshot import Snapshot

from .test_categorize_engine import add, conn
from .test_summary import FakeHA, _with_target
from .test_web import _client, service

__all__ = ["conn", "service"]

WAW = ZoneInfo("Europe/Warsaw")
BANK = "Bank A"
START, END = date(2026, 12, 1), date(2026, 12, 31)
ACC = 3  # konto Banku A; konta 1 i 2 (z fixtury) są innego banku


@pytest.fixture
def ledger(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Księga: konto Banku A (ROR) i konto innego banku, na którym też są płatności."""
    conn.execute("UPDATE account SET bank = 'Bank B' WHERE id IN (1, 2)")
    conn.execute(
        "INSERT INTO account (id, kind, currency, created_at, bank) "
        "VALUES (?, 'current', 'PLN', '2026-01-01T00:00:00', ?)",
        (ACC, BANK),
    )
    return conn


def pay(
    c: sqlite3.Connection,
    day: str,
    kind: str = "card",
    amount: str = "-10.00",
    transfer_group: str | None = None,
) -> int:
    return add(
        c,
        amount,
        kind,
        day=day,
        account=ACC,
        description=f"Sklep X {day}{kind}",
        transfer_group=transfer_group,
    )


def edition(c: sqlite3.Connection, threshold: int = 5) -> int:
    return promo_track.start_edition(c, BANK, "Edycja 12/2026", START, END, threshold)


def cashless(c: sqlite3.Connection, today: date) -> promo_track.Condition:
    (t,) = promo_track.tracks(c, today=today)
    assert t.cashless is not None
    return t.cashless


# --- licznik ---------------------------------------------------------------------------------


def test_counter_counts_card_and_blik_not_own_transfers(ledger: sqlite3.Connection) -> None:
    edition(ledger)
    pay(ledger, "2026-12-02")
    pay(ledger, "2026-12-03", "blik")
    pay(ledger, "2026-12-04", "transfer_out", transfer_group="g1")  # przelew własny
    pay(ledger, "2026-12-05", "transfer_out")  # przelew zwykły — nie jest kartą ani BLIK
    pay(ledger, "2026-12-06", "phone_transfer")
    pay(ledger, "2026-12-07", "card", transfer_group="g2")  # sparowane jako własne
    pay(ledger, "2026-12-08", "card_refund", "10.00")  # zwrot
    pay(ledger, "2026-12-09", "card", "10.00")  # wpływ
    c = cashless(ledger, date(2026, 12, 10))
    assert c.progress == Decimal(2) and c.target == Decimal(5) and not c.met
    assert c.missing == 3


def test_counter_only_this_bank_and_this_month(ledger: sqlite3.Connection) -> None:
    promo_track.start_edition(ledger, BANK, "Edycja", START, date(2027, 2, 28), 5)
    add(ledger, "-10.00", "card", day="2026-12-02", account=1)  # inny bank
    pay(ledger, "2026-11-30")  # przed edycją
    pay(ledger, "2026-12-01")
    pay(ledger, "2026-12-31")
    assert cashless(ledger, date(2026, 12, 15)).progress == Decimal(2)
    # licznik jest miesięczny: po zmianie miesiąca w oknie dłuższej edycji liczy od nowa
    pay(ledger, "2027-01-05")
    assert cashless(ledger, date(2027, 1, 20)).progress == Decimal(1)
    assert cashless(ledger, date(2026, 12, 20)).progress == Decimal(2)


def test_counter_met_at_five_and_no_ledger_flag_for_edition(ledger: sqlite3.Connection) -> None:
    edition(ledger)
    for d in range(2, 7):
        pay(ledger, f"2026-12-0{d}", "card" if d % 2 else "blik")
    c = cashless(ledger, date(2026, 12, 10))
    assert c.progress == Decimal(5) and c.met and c.missing == 0


def test_edition_validation(ledger: sqlite3.Connection) -> None:
    for args in (
        ("", "x", START, END, 5),
        (BANK, "x", END, START, 5),
        (BANK, "x", START, END, 0),
        (BANK, "x", START, END, 500),
    ):
        with pytest.raises(promo_track.PromoError):
            promo_track.start_edition(ledger, *args)


def test_card_counter_m15_unchanged(ledger: sqlite3.Connection) -> None:
    """Wspólna funkcja licznika: stary `payments` liczy jak dotąd (tylko karta, bez BLIK)."""
    from budget import card

    add(ledger, "-10.00", "card", day="2026-12-02")
    add(ledger, "-10.00", "blik", day="2026-12-03")
    assert card.count_purchases(ledger, START, END) == 1


# --- dzwonek ---------------------------------------------------------------------------------


def bell(c: sqlite3.Connection, day: date) -> list[inbox.Item]:
    now = datetime(day.year, day.month, day.day, 8, tzinfo=WAW)
    return [
        i for i in inbox.items(Snapshot(c), now, inbox.BalanceMemo()) if i.kind == "promo_cashless"
    ]


def test_bell_card_do_N_more(ledger: sqlite3.Connection) -> None:
    edition(ledger)
    pay(ledger, "2026-12-02")
    pay(ledger, "2026-12-03", "blik")
    (early,) = bell(ledger, date(2026, 12, 10))
    assert early.count == 3 and "jeszcze 3" in early.title and early.severity == "info"
    assert BANK in early.title and "31.12" in early.detail
    (late,) = bell(ledger, date(2026, 12, 26))
    assert late.severity == "warn"


def test_bell_gone_when_met_or_after_end(ledger: sqlite3.Connection) -> None:
    edition(ledger)
    for d in range(2, 7):
        pay(ledger, f"2026-12-0{d}")
    assert bell(ledger, date(2026, 12, 10)) == []
    assert bell(ledger, date(2027, 1, 5)) == []  # po końcu: karta „zrób jeszcze” znika


def test_bell_other_tracks_unaffected(ledger: sqlite3.Connection) -> None:
    edition(ledger)
    now = datetime(2026, 12, 10, 8, tzinfo=WAW)
    kinds = {i.kind for i in inbox.items(Snapshot(ledger), now, inbox.BalanceMemo())}
    assert "promo_track" not in kinds  # cashless nie wchodzi w ogólną ścieżkę „odbierz premię”


# --- powiadomienia ---------------------------------------------------------------------------


def due(c: sqlite3.Connection, day: date) -> list[summary.Message]:
    now = datetime(day.year, day.month, day.day, 8, tzinfo=WAW)
    return [
        m
        for m in summary.due(Snapshot(c), now)
        if m.kind.startswith(("promo_track_", "promo_cashless_"))
    ]


@pytest.mark.parametrize("days", [14, 7, 2])
def test_push_thresholds_14_7_2(ledger: sqlite3.Connection, days: int) -> None:
    edition(ledger)
    pay(ledger, "2026-12-02")
    day = date(2026, 12, 31 - days)
    (m,) = due(ledger, day)
    assert m.kind == "promo_track_1" and m.period == f"2026-12-31-{days}"
    assert f"za {days} dni" in m.text and "brakuje 4" in m.text and BANK in m.title


@pytest.mark.parametrize("day", [date(2026, 12, 10), date(2026, 12, 16), date(2026, 12, 23)])
def test_push_silent_between_thresholds(ledger: sqlite3.Connection, day: date) -> None:
    edition(ledger)
    assert due(ledger, day) == []


def test_push_sent_once_and_silent_when_met(ledger: sqlite3.Connection) -> None:
    edition(ledger)
    (m,) = due(ledger, date(2026, 12, 17))
    summary.mark_sent(ledger, m)
    assert due(ledger, date(2026, 12, 17)) == []
    for d in range(2, 7):
        pay(ledger, f"2026-12-0{d}")
    assert due(ledger, date(2026, 12, 24)) == []


@pytest.mark.parametrize("left", [6, 3, 0])
def test_push_missing_in_last_7_days_of_month(ledger: sqlite3.Connection, left: int) -> None:
    """Edycja trwa dłużej niż miesiąc: w ostatnich 7 dniach miesiąca przychodzi „brakuje N”."""
    promo_track.start_edition(ledger, BANK, "Edycja", date(2026, 11, 1), date(2027, 2, 28), 5)
    pay(ledger, "2026-11-02")
    pay(ledger, "2026-11-03", "blik")
    (m,) = due(ledger, date(2026, 11, 30 - left))
    assert m.kind == "promo_cashless_1" and m.period == f"2026-11-{left}"
    assert "brakuje 3" in m.text and "listopad" in m.text.lower()
    assert due(ledger, date(2026, 11, 22)) == []  # 8 dni przed końcem miesiąca


def test_no_double_push_when_threshold_day_coincides(ledger: sqlite3.Connection) -> None:
    edition(ledger)  # 31.12 jest też końcem miesiąca; 7 dni przed końcem = 24.12
    msgs = due(ledger, date(2026, 12, 24))
    assert [m.kind for m in msgs] == ["promo_track_1"]


async def test_push_goes_to_configured_family_alias(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    ha = FakeHA()
    _with_target(service, ha)
    service.settings = type(service.settings)(
        **{**service.settings.model_dump(), "summary_notify_service": "notify.family"}
    )
    service.conn.execute(
        "INSERT INTO account (id, kind, currency, created_at, bank) "
        "VALUES (50, 'current', 'PLN', '2026-01-01T00:00:00', ?)",
        (BANK,),
    )
    promo_track.start_edition(service.conn, BANK, "Edycja 12/2026", START, END, 5)
    monkeypatch.setattr(service, "now", lambda: datetime(2026, 12, 17, 8, 0, tzinfo=WAW))
    await service.send_due_summaries()
    promo = [s for s in ha.sent if "promocja" in s[1]]
    assert [s[0] for s in promo] == ["notify.family"]
    assert all("mobile_app" not in s[0] for s in ha.sent)


# --- panel -----------------------------------------------------------------------------------


async def test_web_edition_form_and_progress(service: Service) -> None:
    service.conn.execute(
        "INSERT INTO account (id, kind, currency, created_at, bank) "
        "VALUES (60, 'current', 'PLN', '2026-01-01T00:00:00', ?)",
        (BANK,),
    )
    async with _client(service) as client:
        r = await client.post(
            "/invest/promos/edition",
            data={
                "bank": BANK,
                "title": "Edycja 12/2026",
                "start": "2026-12-01",
                "end": "2026-12-31",
                "threshold": "5",
            },
        )
        assert r.status_code == 303
        page = (await client.get("/invest")).text
        assert "Edycja 12/2026" in page and "Transakcje bezgotówkowe" in page and "/ 5" in page
        bad = await client.post("/invest/promos/edition", data={"bank": "", "title": "x"})
        assert bad.status_code == 303
    assert len(promo_track.tracks(service.conn)) == 1


async def test_web_edition_errors_flash(service: Service) -> None:
    async with _client(service) as client:
        r = await client.post(
            "/invest/promos/edition",
            data={
                "bank": BANK,
                "title": "x",
                "start": "2026-12-31",
                "end": "2026-12-01",
                "threshold": "5",
            },
        )
        assert r.status_code == 303
    assert promo_track.tracks(service.conn) == []
