"""Oferty z sieci (M22 E2): obligacje, ranking lokat i kont, rozpoznanie banku, zapis i błędy."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal

import pytest

from budget import inbox, invest
from budget import invest_sources as src
from budget.storage import db

from .test_categorize_engine import conn

__all__ = ["conn"]

D = Decimal
NOW = datetime(2026, 10, 19, 7, 0)
EDO = "/oferta-obligacji/obligacje-10-letnie-edo/edo1036/"
COI = "/oferta-obligacji/obligacje-4-letnie-coi/coi1030/"


def card(path: str, rate: str, symbol: str) -> str:
    return (
        f'<div class="product-card"><a href="{path}" class="product-card__link">'
        f'<span class="product-card__promo-value"><span class="c">\n  {rate}<sub>%</sub>\n'
        f'</span></span><h3 class="product-card__title">Obligacje {symbol}</h3>'
        f"<p>Obligacje<br><strong>(symbol: {symbol})</strong></p></a></div>"
    )


BONDS = "".join(
    [
        card(EDO, "5,35", "EDO"),
        card(COI, "4,75", "COI"),
        card("/oferta-obligacji/obligacje-3-letnie-tos/tos1029/", "4,40", "TOS"),
        card("/oferta-obligacji/obligacje-2-letnie-dor/dor1028/", "4,15", "DOR"),
        card("/oferta-obligacji/obligacje-roczne-ror/ror1027/", "4,00", "ROR"),
        card("/oferta-obligacji/obligacje-12-letnie-rod/rod1038/", "5,60", "ROD"),  # poza ofertą
    ]
)
EDO_PAGE = "Oprocentowanie: 5,35% w pierwszym rocznym okresie, potem: marża 2,00% + inflacja"
COI_PAGE = "Oprocentowanie: 4,75%, w skali roku, potem marża 1,50% + inflacja"


def entry(name: str, href: str, rate: str, *, period: str | None = None, cond: str = "") -> str:
    """Wpis rankingu Bankiera (uproszczona kopia układu: klasy `offers__item-*`)."""
    period_html = (
        '<div class="offers__item-content-attribute -period">'
        '<div class="offers__item-content-attribute-label">Okres</div>'
        f'<div class="offers__item-content-attribute-value">{period}<!-- --> <!-- -->mies.</div>'
        "</div>"
        if period
        else ""
    )
    tip = (
        '<div class="tooltip__content" role="tooltip"><img alt="Zamknij tooltip"/>'
        f"<div>\t<p>{cond}</p></div></div>"
        if cond
        else ""
    )
    return (
        '<div class="offers__item "><div class="offers__item-content">'
        f'<div class="offers__item-content-name"><img alt="Logo banku {name}"/>'
        f'<a href="{href}" target="_self" class="button link-button -text">{name}</a></div>'
        f'<div class="offers__item-content-attributes">{period_html}'
        '<div class="offers__item-content-attribute -conditions">'
        f'<div class="offers__item-content-attribute-label">Dodatk. warunki {tip}</div></div>'
        '<div class="offers__item-content-attribute -divided">'
        '<div class="offers__item-content-attribute-label">Oprocentowanie</div>'
        f'<div class="offers__item-content-attribute-value">{rate}</div></div></div>'
        '<a href="https://www.bankier.pl/e/lead/1/" class="button link-button ">Sprawdź ofertę</a>'
        "</div></div>"
    )


ALFA = "/smart/lokata-alfa-od-velobanku-warunki?id=1"
DEPOSITS = "".join(
    [
        entry(
            "Lokata Alfa",
            ALFA,
            "6,00 %",
            period="6",
            cond="Oferta dla nowych klientów, min. 1000 zł. Do 150 000 zł.",
        ),
        entry("Lokata terminowa", "/smart/pekao-lokata-terminowa?id=2", "5,40 %", period="12"),
        entry("Lokata terminowa", "/smart/lokata-terminowa-b?id=3", "4,00 %", period="3"),
        entry("Lokata zerowa", "/smart/lokata-zero?id=4", "0,00 %", period="3"),
    ]
)
ACCOUNTS = "".join(
    [
        entry(
            "Konto Promo",
            "/smart/konto-promo-w-mbanku-warunki?id=10",
            "6,50 %",
            cond="Środki do 100 000 zł, obowiązuje 100 dni. Dla klientów, którzy nie mieli konta.",
        ),
        entry("Konto stałe", "/smart/konto-stale?id=11", "2,00 %"),
    ]
)


# --- parsowanie ---


def test_parse_bonds_reads_rates_and_series_links() -> None:
    got = src.parse_bonds(BONDS)
    assert set(got) == {"edo", "coi", "tos", "dor", "ror"}  # ROD (rodzinne) poza ofertą
    assert got["edo"] == (D("5.35"), EDO)
    assert got["ror"][0] == D("4.00")


def test_parse_bonds_rejects_changed_layout() -> None:
    with pytest.raises(src.SourceError):
        src.parse_bonds("<html>zmieniony układ</html>")


def test_parse_margin() -> None:
    assert src.parse_margin(EDO_PAGE) == D("2.00")
    assert src.parse_margin(COI_PAGE) == D("1.50")
    with pytest.raises(src.SourceError):
        src.parse_margin("brak marży")


def test_parse_ranking_deposits() -> None:
    a, b, c = src.parse_ranking(DEPOSITS, "deposit")  # stawka 0% odpada
    assert (a.rate, a.months, a.limit) == (D("6.00"), 6, D("150000"))
    assert a.new_only and a.bank == "VeloBank" and not a.review
    assert a.url == "https://www.bankier.pl/smart/lokata-alfa-od-velobanku-warunki?id=1"
    assert b.bank == "Bank Pekao" and not b.new_only and b.months == 12
    assert c.bank == "Lokata terminowa" and c.review  # banku nie rozpoznano → do sprawdzenia


def test_parse_ranking_limit_forms() -> None:
    cond = "Stawka obowiązuje przez 3 miesiące do kwoty 200 000 zł. Premia do 700 zł."
    banner = "Oferta promowana - wartość lokaty max. do 150 000 zł"
    page = entry("Konto L", "/smart/konto-l?id=20", "5,00 %", cond=cond).replace(
        "</div></div>", f"</div></div><div>{banner}</div>", 1
    )
    (a,) = src.parse_ranking(page, "account")
    assert a.limit == D("200000") and a.months == 3
    only_banner = entry("Konto M", "/smart/konto-m?id=21", "5,00 %") + f"<p>{banner}</p>"
    assert src.parse_ranking(only_banner, "account")[0].limit == D("150000")


def test_parse_ranking_never_uses_robots_disallowed_lead_links() -> None:
    assert all("/e/lead" not in o.url for o in src.parse_ranking(DEPOSITS, "deposit"))


def test_parse_ranking_accounts_read_promo_length_and_limit() -> None:
    promo, plain = src.parse_ranking(ACCOUNTS, "account")
    assert promo.rate == D("6.50") and promo.limit == D("100000")
    assert promo.months == 3  # 100 dni ≈ 3,3 mies. → 3 (zaokrąglenie, nie zawyżamy promocji)
    assert promo.new_only and promo.bank == "mBank"
    assert plain.months is None and not plain.new_only


def test_parse_ranking_rejects_changed_layout() -> None:
    with pytest.raises(src.SourceError):
        src.parse_ranking("<html>zmieniony układ</html>", "deposit")


@pytest.mark.parametrize(
    ("title", "slug", "bank"),
    [
        ("Lokata", "lokata-w-banku-millennium-jakie-warunki", "Bank Millennium"),
        ("Lokata", "lokata-terminowa-plus-ing-banku-slaskiego-analiza", "ING Bank Śląski"),
        ("Lokata", "ca-auto-bank-lokata-terminowa-analiza", "CA Auto Bank"),
        ("Konto", "konto-mega-oszczednosciowe-w-alior-banku", "Alior Bank"),
        ("Lokata", "lokata-standardowa-razem-ingress", None),  # „ing” w środku słowa to nie ING
    ],
)
def test_guess_bank(title: str, slug: str, bank: str | None) -> None:
    assert src.guess_bank(title, slug) == bank


# --- zapis i filtr ---


def feed(pages: dict[str, str]) -> src.Get:
    async def get(url: str) -> str:
        if url not in pages:
            raise src.SourceError(f"brak {url}")
        return pages[url]

    return get


PAGES = {
    src.BONDS_URL: BONDS,
    src.BONDS_ROOT + EDO: EDO_PAGE,
    src.BONDS_ROOT + COI: COI_PAGE,
    src.DEPOSITS_URL: DEPOSITS,
    src.ACCOUNTS_URL: ACCOUNTS,
}


def offers(conn: sqlite3.Connection) -> list[invest.Offer]:
    return invest.all_offers(conn)


def labels(conn: sqlite3.Connection) -> set[str]:
    opts = invest.options(conn, D(10000), D(1), NOW.date(), invest.Settings())
    return {o.label for o in opts}


async def test_refresh_stores_bonds_with_margin_and_ranking(conn: sqlite3.Connection) -> None:
    await src.refresh(conn, NOW, feed(PAGES))
    by = {(o.kind, o.bank): o for o in offers(conn)}
    edo = by["edo", "Skarb Państwa"]
    assert (edo.rate, edo.margin, edo.status) == (D("5.35"), D("2.00"), "confirmed")
    assert edo.source == "bonds" and edo.url == src.BONDS_ROOT + EDO
    assert by["coi", "Skarb Państwa"].margin == D("1.50")
    assert by["tos", "Skarb Państwa"].margin is None
    assert by["deposit", "VeloBank"].source == "ranking" and by["deposit", "VeloBank"].new_only
    assert by["deposit", "Lokata terminowa"].status == "review"  # banku nie rozpoznano
    assert src.error(conn) is None


async def test_refresh_is_idempotent_and_updates_rates_in_place(conn: sqlite3.Connection) -> None:
    await src.refresh(conn, NOW, feed(PAGES))
    n = len(offers(conn))
    await src.refresh(conn, NOW, feed(PAGES | {src.BONDS_URL: BONDS.replace("5,35", "5,10")}))
    assert len(offers(conn)) == n
    assert next(o for o in offers(conn) if o.kind == "edo").rate == D("5.10")


async def test_refresh_archives_gone_ranking_offers_but_keeps_manual(
    conn: sqlite3.Connection,
) -> None:
    invest.save_offer(conn, "deposit", "Bank A", "4", None, None, "12", "", False)
    await src.refresh(conn, NOW, feed(PAGES))
    only_alfa = entry("Lokata Alfa", ALFA, "6,00 %", period="6")
    await src.refresh(conn, NOW, feed(PAGES | {src.DEPOSITS_URL: only_alfa}))
    banks = {o.bank for o in offers(conn) if o.kind == "deposit"}
    assert banks == {"Bank A", "VeloBank"}  # reszta z rankingu zniknęła, ręczna zostaje


async def test_rejected_offer_does_not_come_back(conn: sqlite3.Connection) -> None:
    await src.refresh(conn, NOW, feed(PAGES))
    velo = next(o for o in offers(conn) if o.bank == "VeloBank")
    invest.archive_offer(conn, velo.id)
    await src.refresh(conn, NOW, feed(PAGES))
    assert all(o.bank != "VeloBank" for o in offers(conn))


async def test_one_failing_source_does_not_block_the_others(conn: sqlite3.Connection) -> None:
    await src.refresh(conn, NOW, feed({k: v for k, v in PAGES.items() if k != src.DEPOSITS_URL}))
    kinds = {o.kind for o in offers(conn)}
    assert "edo" in kinds and "account" in kinds
    err = src.error(conn)
    assert err is not None and "lokat" in err[0].lower() and err[1] == NOW


async def test_error_keeps_first_failure_time_and_clears_after_success(
    conn: sqlite3.Connection,
) -> None:
    await src.refresh(conn, NOW, feed({}))
    later = datetime(2026, 10, 21, 7, 0)
    await src.refresh(conn, later, feed({}))
    err = src.error(conn)
    assert err is not None and err[1] == NOW
    await src.refresh(conn, later, feed(PAGES))
    assert src.error(conn) is None


def test_due_only_after_interval(conn: sqlite3.Connection) -> None:
    assert src.due(conn, NOW)
    db.kv_set(conn, src.KEY, {"checked": NOW.isoformat()})
    assert not src.due(conn, datetime(2026, 10, 19, 12, 0))
    assert src.due(conn, datetime(2026, 10, 20, 7, 0))


async def test_new_client_offers_hidden_for_existing_clients(conn: sqlite3.Connection) -> None:
    await src.refresh(conn, NOW, feed(PAGES))
    assert "Lokata VeloBank" in labels(conn)
    invest.save_bank(conn, "  velobank ")
    assert "Lokata VeloBank" not in labels(conn)
    assert "Lokata Bank Pekao" in labels(conn)  # oferta bez ograniczenia zostaje
    (bank,) = invest.all_banks(conn)
    invest.delete_bank(conn, bank.id)
    assert "Lokata VeloBank" in labels(conn)


def test_save_bank_rejects_blank_and_duplicate(conn: sqlite3.Connection) -> None:
    with pytest.raises(invest.InvestError):
        invest.save_bank(conn, "  ")
    invest.save_bank(conn, "Bank A")
    with pytest.raises(invest.InvestError):
        invest.save_bank(conn, "bank a")


async def test_review_offer_is_ignored_until_confirmed(conn: sqlite3.Connection) -> None:
    await src.refresh(conn, NOW, feed(PAGES))
    assert "Lokata Lokata terminowa" not in labels(conn)
    review = next(o for o in offers(conn) if o.status == "review" and o.kind == "deposit")
    invest.confirm_offer(conn, review.id, "Bank Beta")
    got = next(o for o in offers(conn) if o.id == review.id)
    assert (got.status, got.bank) == ("confirmed", "Bank Beta")
    assert "Lokata Bank Beta" in labels(conn)


def test_error_card_appears_after_three_days(conn: sqlite3.Connection) -> None:
    ctx = inbox.Context(NOW, None, None)  # type: ignore[arg-type]  # dostawca czyta tylko `now`
    db.kv_set(conn, src.KEY, {"error": "SourceError: x", "error_since": "2026-10-15T07:00:00"})
    (item,) = inbox.invest_source_error(conn, ctx, None)  # type: ignore[arg-type]
    assert item.kind == "invest_source_error" and item.link == "/invest"
    db.kv_set(conn, src.KEY, {"error": "x", "error_since": "2026-10-18T07:00:00"})
    assert inbox.invest_source_error(conn, ctx, None) == []  # type: ignore[arg-type]
