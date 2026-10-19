"""Agent inwestycyjny (M22 E1, decyzja 30): koszyki, zysk netto opcji, rekomendacja.

Wyłącznie doradztwo — żadnych operacji na kontach. Liczy add-on, deterministycznie; zysk netto po
Belce (19%), w IKE bez podatku. Trzy koszyki: poduszka (mnożnik × miesięczne wydatki), cele 1–5
lat (skarbonki M10) i długi termin (reszta). Nowe pieniądze to nadwyżka miesiąca z prognozy rocznej
(M18) po skarbonkach; przy deficycie agent niczego nowego nie poleca. Oferty wpisuje użytkownik
albo dopisuje `invest_sources` (E2); oferty „tylko dla nowych” znikają z porównania dla banków
z listy użytkownika.
"""

from __future__ import annotations

import calendar
import json
import math
import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_FLOOR, Decimal

from budget import loan, loan_sim, money, piggy, savings, year
from budget.forecast import Forecast
from budget.piggy import PiggyError
from budget.snapshot import Snapshot
from budget.spending import month_start
from budget.storage import db
from budget.storage.db import now_iso

ZERO = money.ZERO
BELKA = savings.BELKA
SETTINGS_KEY = "invest_settings"
GOAL_YEARS = 5  # skarbonki z terminem dalej niż tyle lat nie należą do koszyka celów
BUCKET_NAMES = {1: "poduszka", 3: "długi termin"}  # krótkie nazwy koszyków w pushu i opisie dla LLM
ASSET_KINDS = {
    "bonds": "Obligacje",
    "deposit": "Lokata",
    "account": "Konto oszczędnościowe",
    "etf": "ETF",
    "stock": "Akcje",
    "other": "Inne",
}
OFFER_KINDS = {
    "deposit": "Lokata",
    "account": "Konto oszczędnościowe",
    "edo": "Obligacje EDO",
    "coi": "Obligacje COI",
    "tos": "Obligacje TOS",
    "ror": "Obligacje ROR",
    "dor": "Obligacje DOR",
}


@dataclass(frozen=True)
class Bond:
    term: int  # lata do wykupu
    indexed: bool  # od drugiego roku inflacja + marża (inaczej stała stawka z pierwszego roku)
    capitalised: bool  # odsetki dopisywane do kapitału (inaczej wypłacane co roku)
    fee: Decimal  # opłata za przedterminowy wykup, zł za obligację (100 zł)


BONDS = {
    "edo": Bond(10, True, True, Decimal(2)),
    "coi": Bond(4, True, False, Decimal("0.7")),
    "tos": Bond(3, False, True, Decimal("0.7")),
    "ror": Bond(1, False, False, Decimal("0.5")),
    "dor": Bond(2, False, False, Decimal("0.7")),
}
INDEXED = ("edo", "coi")  # wymagają marży

# etykiety opcji bez nazw własnych (konto, kredyt, bank) — dla czatu i uzasadnienia od LLM
OPTION_KINDS = {
    **OFFER_KINDS,
    "account_own": "własne konto oszczędnościowe",
    "etf": "ETF",
    "etf_ike": "ETF w IKE",
    "overpay": "nadpłata kredytu",
    "edo_ike": "Obligacje EDO w IKE",
}


class InvestError(PiggyError):
    pass


@dataclass(frozen=True)
class Settings:
    cushion_months: int = 3
    etf_returns: tuple[Decimal, Decimal, Decimal] = (Decimal(0), Decimal(6), Decimal(9))
    etf_ter: Decimal = Decimal("0.2")  # % rocznie
    inflation: Decimal = Decimal(3)  # % rocznie, do obligacji indeksowanych
    better_offer: Decimal = Decimal(
        200
    )  # zł rocznie: o tyle oferta musi bić obecne miejsce (dzwonek)


@dataclass(frozen=True)
class Bank:
    id: int
    name: str


@dataclass(frozen=True)
class Asset:
    id: int
    kind: str
    name: str
    amount: Decimal
    rate: Decimal | None = None
    start: date | None = None
    maturity: date | None = None
    ike: bool = False


@dataclass(frozen=True)
class Offer:
    id: int
    kind: str
    bank: str
    rate: Decimal  # % rocznie (obligacje: pierwszy rok)
    margin: Decimal | None = None
    limit_amount: Decimal | None = None
    months: int | None = None
    conditions: str = ""
    new_only: bool = False
    status: str = "confirmed"
    source: str = "manual"
    url: str | None = None


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    net_gain: Decimal  # zysk netto w horyzoncie, zł
    per_year: Decimal  # netto zł rocznie (zysk / lata)
    years: Decimal  # ile lat pieniądze są związane (lokata dłuższa niż horyzont wydłuża go)
    liquid: bool = True
    risky: bool = False
    scenarios: tuple[Decimal, ...] | None = None  # ETF: zysk netto w 3 scenariuszach
    note: str = ""
    offer_id: int | None = None


def _option(key: str, label: str, gain: Decimal, years: Decimal, **kw: object) -> Option:
    gain = gain.quantize(money.CENT)
    return Option(key, label, gain, (gain / years).quantize(money.CENT), years, **kw)  # type: ignore[arg-type]


# --- zysk netto opcji -----------------------------------------------------------------------


def _tax(gain: Decimal, ike: bool = False) -> Decimal:
    return gain if ike or gain <= 0 else gain * (1 - BELKA)


def _deposit(o: Offer, amount: Decimal, years: Decimal) -> Option:
    months = o.months or 12
    periods = max(math.ceil(years * 12 / months), 1)
    step = 1 + o.rate / 100 * months / 12 * (1 - BELKA)  # odsetki netto dopisane po każdym okresie
    return _option(
        "deposit",
        f"Lokata {o.bank}",
        amount * (step**periods - 1),
        Decimal(periods * months) / 12,
        liquid=False,
        note=f"{months} mies., po okresie odnawiana na tych samych warunkach",
        offer_id=o.id,
    )


def _account(o: Offer, amount: Decimal, years: Decimal) -> Option:
    base = min(amount, o.limit_amount) if o.limit_amount else amount
    n = math.ceil(years * 12)
    paid = min(n, o.months) if o.months else n
    step = 1 + o.rate / 100 / 12 * (1 - BELKA)
    return _option(
        "account",
        f"Konto {o.bank}",
        base * (step**paid - 1),
        years,
        note="po okresie promocji bez odsetek" if o.months and o.months < n else "",
        offer_id=o.id,
    )


def _bond(o: Offer, amount: Decimal, years: Decimal, s: Settings, *, ike: bool = False) -> Option:
    spec = BONDS[o.kind]
    held = min(years, Decimal(spec.term))
    value, paid = amount, ZERO
    for i in range(math.ceil(held)):
        frac = min(Decimal(1), held - i)
        rate = o.rate if i == 0 or not spec.indexed else s.inflation + (o.margin or ZERO)
        if spec.capitalised:
            value *= 1 + rate / 100 * frac
        else:
            paid += amount * rate / 100 * frac
    gross = value - amount + paid
    if held < spec.term:  # opłata nie przekracza zarobionych odsetek
        gross -= min(spec.fee * amount / 100, gross)
    label = OFFER_KINDS[o.kind] + (" w IKE" if ike else "")
    return _option(
        f"{o.kind}_ike" if ike else o.kind,
        label,
        _tax(gross, ike),
        held,
        liquid=False,
        note=f"{spec.term} lat; wcześniejszy wykup kosztuje {spec.fee} zł od obligacji"
        if held < spec.term
        else f"{spec.term} lat",
        offer_id=o.id,
    )


def offer_options(o: Offer, amount: Decimal, years: Decimal, s: Settings) -> list[Option]:
    """Opcje z jednej oferty: lokata/konto jedna, obligacje EDO dodatkowo „w IKE”."""
    if o.kind == "deposit":
        return [_deposit(o, amount, years)]
    if o.kind == "account":
        return [_account(o, amount, years)]
    out = [_bond(o, amount, years, s)]
    if o.kind == "edo":
        out.append(_bond(o, amount, years, s, ike=True))
    return out


def etf_option(amount: Decimal, years: Decimal, s: Settings, *, ike: bool = False) -> Option:
    """ETF w trzech scenariuszach rocznego zwrotu (minus TER), netto po Belce albo w IKE."""
    gains = tuple(
        _tax(amount * ((1 + (r - s.etf_ter) / 100) ** years - 1), ike).quantize(money.CENT)
        for r in s.etf_returns
    )
    mid = gains[1]
    return Option(
        "etf_ike" if ike else "etf",
        "ETF w IKE" if ike else "ETF",
        mid,
        (mid / years).quantize(money.CENT),
        years,
        risky=True,
        scenarios=gains,
        note="zwroty z ustawień; kapitał może spaść",
    )


def savings_option(
    acc: savings.Account, amount: Decimal, years: Decimal, today: date
) -> Option | None:
    """Konto z M10 (stopa bazowa i promocja z karty konta), odsetki netto co miesiąc."""
    if acc.base_rate is None and acc.promo_rate is None:
        return None
    bal, day = amount, today
    for _ in range(math.ceil(years * 12)):
        days = calendar.monthrange(day.year, day.month)[1]
        bal += savings.net(savings.daily(acc, bal, day) * days)
        day += timedelta(days=days)
    return _option("account_own", f"Konto {acc.name}", bal - amount, years)


def overpay_option(lo: loan.Loan, amount: Decimal, years: Decimal, today: date) -> Option | None:
    gain = loan_sim.overpay_gain(lo, amount, today, int(years * 12))
    if gain is None:
        return None
    return _option(
        "overpay",
        f"Nadpłata kredytu {lo.name}",
        gain,
        years,
        liquid=False,
        note="zaoszczędzone odsetki, bez podatku; pieniędzy nie da się odzyskać",
    )


def options(
    conn: sqlite3.Connection, amount: Decimal, years: Decimal, today: date, s: Settings
) -> list[Option]:
    """Wszystkie opcje dla kwoty i horyzontu, od najlepszej (zysk netto rocznie)."""
    out = [
        o for acc in savings.all_accounts(conn) if (o := savings_option(acc, amount, years, today))
    ]
    clients = [b.name for b in all_banks(conn)]
    for offer in all_offers(conn):
        if offer.status == "confirmed" and not is_hidden(offer, clients):
            out += offer_options(offer, amount, years, s)
    out += [etf_option(amount, years, s), etf_option(amount, years, s, ike=True)]
    out += [o for lo in loan.all_loans(conn) if (o := overpay_option(lo, amount, years, today))]
    return sorted(out, key=lambda o: o.per_year, reverse=True)


# --- koszyki i rekomendacja -----------------------------------------------------------------


@dataclass(frozen=True)
class Inputs:
    spend: Decimal  # miesięczne wydatki (serie + Flex + nieregularne + roczne)
    savings_total: Decimal  # konta oszczędnościowe M10
    free_above_buffer: Decimal  # wolne środki M8 ponad bufor
    goal_target: Decimal
    goal_have: Decimal
    assets_total: Decimal
    surplus: Decimal | None  # nadwyżka miesiąca po skarbonkach; None bez prognozy


@dataclass(frozen=True)
class Bucket:
    key: int
    label: str
    target: Decimal | None
    have: Decimal

    @property
    def gap(self) -> Decimal:
        return max(self.target - self.have, ZERO) if self.target is not None else ZERO

    @property
    def progress(self) -> float:
        if not self.target or self.target <= 0:
            return 0.0
        return max(0.0, min(1.0, float(self.have / self.target)))


def buckets(inp: Inputs, s: Settings) -> list[Bucket]:
    return [
        Bucket(
            1,
            "Poduszka",
            (inp.spend * s.cushion_months).quantize(money.CENT),
            inp.savings_total + max(inp.free_above_buffer, ZERO),
        ),
        Bucket(2, "Cele 1–5 lat", inp.goal_target, inp.goal_have),
        Bucket(3, "Długi termin", None, inp.assets_total),
    ]


@dataclass(frozen=True)
class Part:
    bucket: int
    amount: Decimal  # zł miesięcznie
    option: Option | None  # None, gdy nie ma pasującej opcji (dodaj konto albo ofertę)


@dataclass(frozen=True)
class Recommendation:
    state: str  # invest | deficit | no_data
    surplus: Decimal | None = None
    parts: list[Part] = field(default_factory=list)


def _best(opts: Sequence[Option]) -> Option | None:
    return max(opts, key=lambda o: o.per_year, default=None)


def recommend(inp: Inputs, s: Settings, opts: Sequence[Option]) -> Recommendation:
    """Najpierw dopełnia poduszkę płynną opcją, reszta na długi termin; ETF nie jest polecany
    automatycznie. Bez nadwyżki nic nowego — tylko optymalizacja tego, co już leży."""
    if inp.surplus is None:
        return Recommendation("no_data")
    if inp.surplus <= 0:
        return Recommendation("deficit", inp.surplus)
    safe = [o for o in opts if not o.risky]
    to_cushion = min(inp.surplus, buckets(inp, s)[0].gap)
    parts = []
    if to_cushion > 0:
        parts.append(Part(1, to_cushion, _best([o for o in safe if o.liquid])))
    if inp.surplus > to_cushion:
        parts.append(Part(3, inp.surplus - to_cushion, _best(safe)))
    return Recommendation("invest", inp.surplus, parts)


def build_inputs(
    conn: sqlite3.Connection,
    proj: year.Projection | None,
    piggies: Sequence[piggy.Status],
    today: date,
) -> Inputs:
    """Dane koszyków z prognozy rocznej, skarbonek, kont M10 i aktywów. Wydatki i nadwyżka ze
    średniej pełnych miesięcy prognozy (bez bieżącego, niepełnego)."""
    saved = sum((savings.estimate(conn, a, today).total for a in savings.all_accounts(conn)), ZERO)
    near = [
        s
        for s in piggies
        if s.target is not None
        and (s.due is None or s.due <= today + timedelta(days=365 * GOAL_YEARS))
    ]
    goal_target = sum((s.target or ZERO for s in near), ZERO)
    goal_have = sum((s.balance for s in near), ZERO)
    months = proj.months[1:] or proj.months if proj else []
    if not proj or not months:
        return Inputs(ZERO, saved, ZERO, goal_target, goal_have, assets_total(conn), None)
    n = len(months)
    spend = sum((m.series_out + m.flex + m.irregular + m.seasonal for m in months), ZERO) / n
    net = sum((m.net for m in months), ZERO) / n - sum((s.monthly for s in piggies), ZERO)
    return Inputs(
        spend.quantize(money.CENT),
        saved,
        proj.start_balance - proj.buffer,
        goal_target,
        goal_have,
        assets_total(conn),
        net.quantize(Decimal(1), ROUND_FLOOR),
    )


# --- doradztwo dla dzwonka, pusha i czatu (E4) -----------------------------------------------

DEFAULT_YEARS = Decimal(5)
FALLBACK_AMOUNT = Decimal(10_000)  # porównanie bez nadwyżki: kwota przykładowa
MATURITY_DAYS = 14  # koniec lokaty albo wykup obligacji: tyle dni naprzód


@dataclass(frozen=True)
class Advice:
    """To, co `/invest` pokazuje bez zmian formularza: koszyki, opcje i rekomendacja."""

    settings: Settings
    inputs: Inputs
    buckets: list[Bucket]
    options: list[Option]
    rec: Recommendation
    amount: Decimal
    payday: date | None  # dzień ostatniej wypłaty (prognoza do wypłaty); None bez wypłaty w księdze


def piggy_rows(snap: Snapshot, fc: Forecast | None, today: date) -> list[piggy.Status]:
    if fc is not None and fc.piggies_from is not None:
        return fc.piggies
    return piggy.statuses(snap, today, month_start(today))


def default_amount(surplus: Decimal | None) -> Decimal:
    return surplus * 12 if surplus and surplus > 0 else FALLBACK_AMOUNT


def advice(
    snap: Snapshot,
    fc: Forecast | None,
    proj: year.Projection | None,
    today: date,
    amount: Decimal | None = None,
    years: Decimal = DEFAULT_YEARS,
) -> Advice:
    """Rekomendacja dla kwoty i horyzontu porównania; domyślnie roczna nadwyżka na 5 lat."""
    conn = snap.conn
    s = load_settings(conn)
    inp = build_inputs(conn, proj, piggy_rows(snap, fc, today), today)
    amount = amount or default_amount(inp.surplus)
    opts = options(conn, amount, years, today, s)
    return Advice(
        s,
        inp,
        buckets(inp, s),
        opts,
        recommend(inp, s, opts),
        amount,
        fc.period_start if fc else None,
    )


@dataclass(frozen=True)
class Better:
    holder: str  # konto M10 albo aktywo, które lepiej przenieść
    offer: Offer
    gain: Decimal  # zł rocznie netto ponad obecne oprocentowanie


def _holders(conn: sqlite3.Connection, today: date) -> list[tuple[str, Decimal, Decimal]]:
    """Gdzie leżą wolne pieniądze na koncie: (nazwa, kwota, obecny zysk netto zł rocznie)."""
    out = []
    for acc in savings.all_accounts(conn):
        bal = savings.estimate(conn, acc, today).total
        cur = savings_option(acc, bal, Decimal(1), today) if bal > 0 else None
        if cur is not None:
            out.append((acc.name, bal, cur.per_year))
    for a in all_assets(conn):
        if a.kind == "account" and a.rate is not None and a.amount > 0:
            out.append((a.name, a.amount, _tax(a.amount * a.rate / 100, a.ike)))
    return out


def better_offers(conn: sqlite3.Connection, today: date, s: Settings) -> list[Better]:
    """Potwierdzone, widoczne dla użytkownika lokaty i konta, które dla kwoty z danego miejsca
    dają rocznie co najmniej `s.better_offer` zł więcej niż obecne oprocentowanie. Dla każdego
    miejsca najlepsza oferta."""
    clients = [b.name for b in all_banks(conn)]
    offers = [
        o
        for o in all_offers(conn)
        if o.kind in ("deposit", "account")
        and o.status == "confirmed"
        and not is_hidden(o, clients)
    ]
    out = []
    for holder, amount, current in _holders(conn, today):
        found = [
            Better(holder, o, opt.per_year - current)
            for o in offers
            for opt in offer_options(o, amount, Decimal(1), s)
        ]
        best = max(found, key=lambda b: b.gain, default=None)
        if best is not None and best.gain >= max(s.better_offer, money.CENT):
            out.append(best)
    return out


def maturities(conn: sqlite3.Connection, today: date) -> list[Asset]:
    """Aktywa z terminem w ciągu `MATURITY_DAYS` dni (także dzisiejszym), od najbliższego."""
    end = today + timedelta(days=MATURITY_DAYS)
    due = [a for a in all_assets(conn) if a.maturity is not None and today <= a.maturity <= end]
    return sorted(due, key=lambda a: (a.maturity or today, a.id))


# --- zapis ----------------------------------------------------------------------------------


def _pct(value: str | None, what: str, *, required: bool = False) -> Decimal | None:
    if not required and not (value or "").strip():
        return None
    try:
        rate = money.parse(value)
    except money.AmountError:
        rate = None
    if rate is None or not 0 <= rate <= 100:
        raise InvestError(f"Podaj {what} w procentach, np. 5 albo 4,5.")
    return rate


def _day(value: str | None, what: str) -> date | None:
    if not value or not value.strip():
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InvestError(f"Podaj poprawną datę ({what}).") from exc


def load_settings(conn: sqlite3.Connection) -> Settings:
    raw = db.kv_get(conn, SETTINGS_KEY)
    if not raw:
        return Settings()
    a, b, c = (Decimal(x) for x in raw["etf_returns"])
    return Settings(
        int(raw["cushion_months"]),
        (a, b, c),
        Decimal(raw["etf_ter"]),
        Decimal(raw["inflation"]),
        Decimal(raw.get("better_offer", Settings.better_offer)),
    )


def save_settings(
    conn: sqlite3.Connection,
    cushion: str,
    returns: str,
    ter: str,
    inflation: str,
    better: str = str(Settings.better_offer),
) -> None:
    try:
        months = int(cushion)
    except ValueError:
        months = 0
    if not 1 <= months <= 24:
        raise InvestError("Poduszka: podaj liczbę miesięcy wydatków od 1 do 24.")
    parts = [p for p in returns.replace(",", ".").split(";") if p.strip()]
    if len(parts) != 3:
        raise InvestError("Zwroty ETF: podaj trzy wartości rozdzielone średnikiem, np. 0; 6; 9.")
    rates = [_pct(p, "zwrot ETF", required=True) for p in parts]
    fee = _pct(ter, "koszt TER", required=True)
    infl = _pct(inflation, "inflację", required=True)
    try:
        threshold = piggy.parse_amount(better, "próg lepszej oferty (zł rocznie)", allow_zero=True)
    except PiggyError as exc:
        raise InvestError(str(exc)) from exc
    threshold = Settings.better_offer if threshold is None else threshold
    db.kv_set(
        conn,
        SETTINGS_KEY,
        {
            "cushion_months": months,
            "etf_returns": [str(r) for r in rates],
            "etf_ter": str(fee),
            "inflation": str(infl),
            "better_offer": str(threshold),
        },
    )


def _asset(r: sqlite3.Row) -> Asset:
    return Asset(
        r["id"],
        r["kind"],
        r["name"],
        Decimal(r["amount"]),
        Decimal(r["rate"]) if r["rate"] else None,
        date.fromisoformat(r["start_date"]) if r["start_date"] else None,
        date.fromisoformat(r["maturity_date"]) if r["maturity_date"] else None,
        bool(r["ike"]),
    )


def all_assets(conn: sqlite3.Connection) -> list[Asset]:
    return [
        _asset(r)
        for r in conn.execute(
            "SELECT * FROM invest_asset WHERE archived_at IS NULL ORDER BY kind, name"
        )
    ]


def assets_total(conn: sqlite3.Connection) -> Decimal:
    return sum((a.amount for a in all_assets(conn)), ZERO)


def save_asset(
    conn: sqlite3.Connection,
    asset_id: int | None,
    kind: str,
    name: str,
    amount: str | None,
    rate: str | None,
    start: str | None,
    maturity: str | None,
    ike: bool,
) -> int:
    clean = " ".join(name.split())[:60]
    if kind not in ASSET_KINDS:
        raise InvestError("Wybierz rodzaj aktywa.")
    if not clean:
        raise InvestError("Podaj nazwę aktywa.")
    value = piggy.parse_amount(amount, "wartość aktywa")
    if value is None:
        raise InvestError("Podaj wartość aktywa, np. 5000.")
    pct = _pct(rate, "oprocentowanie")
    day, end = _day(start, "początek"), _day(maturity, "zapadalność")
    params = (
        kind,
        clean,
        str(value),
        None if pct is None else str(pct),
        day.isoformat() if day else None,
        end.isoformat() if end else None,
        int(ike),
    )
    if asset_id is None:
        cur = conn.execute(
            "INSERT INTO invest_asset (kind, name, amount, rate, start_date, maturity_date, ike, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (*params, now_iso()),
        )
        return int(cur.lastrowid or 0)
    cur = conn.execute(
        "UPDATE invest_asset SET kind = ?, name = ?, amount = ?, rate = ?, start_date = ?, "
        "maturity_date = ?, ike = ? WHERE id = ? AND archived_at IS NULL",
        (*params, asset_id),
    )
    if not cur.rowcount:
        raise InvestError("Nie ma takiego aktywa.")
    return asset_id


def archive_asset(conn: sqlite3.Connection, asset_id: int) -> None:
    conn.execute("UPDATE invest_asset SET archived_at = ? WHERE id = ?", (now_iso(), asset_id))


def _offer(r: sqlite3.Row) -> Offer:
    return Offer(
        r["id"],
        r["kind"],
        r["bank"],
        Decimal(r["rate"]),
        Decimal(r["margin"]) if r["margin"] else None,
        Decimal(r["limit_amount"]) if r["limit_amount"] else None,
        r["months"],
        r["conditions"],
        bool(r["new_clients_only"]),
        r["status"],
        r["source"],
        r["url"],
    )


def all_offers(conn: sqlite3.Connection) -> list[Offer]:
    return [
        _offer(r)
        for r in conn.execute(
            "SELECT * FROM invest_offer WHERE archived_at IS NULL AND status != 'rejected' "
            "ORDER BY kind, bank"
        )
    ]


def _offer_fields(
    kind: str, rate: str | None, limit_amount: str | None, months: str | None, conditions: str
) -> tuple[Decimal, Decimal | None, int | None, str]:
    """Stawka, limit, okres i warunki z pól formularza (dodanie i potwierdzenie oferty)."""
    pct = _pct(rate, "oprocentowanie", required=True)
    cap = piggy.parse_amount(limit_amount, "limit kwoty")
    try:
        period = int(months) if months and months.strip() else None
    except ValueError:
        period = None
    if kind == "deposit" and (period is None or period < 1):
        raise InvestError("Lokata wymaga okresu w miesiącach, np. 12.")
    if period is not None and not 1 <= period <= 120:
        raise InvestError("Okres podaj w miesiącach, od 1 do 120.")
    assert pct is not None  # `required=True`
    return pct, cap, period, " ".join(conditions.split())[:300]


def save_offer(
    conn: sqlite3.Connection,
    kind: str,
    bank: str,
    rate: str | None,
    margin: str | None,
    limit_amount: str | None,
    months: str | None,
    conditions: str,
    new_only: bool,
) -> int:
    if kind not in OFFER_KINDS:
        raise InvestError("Wybierz rodzaj oferty.")
    name = " ".join(bank.split())[:40]
    if not name:
        raise InvestError("Podaj bank albo emitenta oferty.")
    extra = _pct(margin, "marżę")
    if kind in INDEXED and extra is None:
        raise InvestError("Obligacje indeksowane (EDO, COI) wymagają marży ponad inflację.")
    pct, cap, period, cond = _offer_fields(kind, rate, limit_amount, months, conditions)
    cur = conn.execute(
        "INSERT INTO invest_offer (kind, bank, rate, margin, limit_amount, months, conditions, "
        "new_clients_only, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            kind,
            name,
            str(pct),
            None if extra is None else str(extra),
            None if cap is None else str(cap),
            period,
            cond,
            int(new_only),
            now_iso(),
        ),
    )
    return int(cur.lastrowid or 0)


def archive_offer(conn: sqlite3.Connection, offer_id: int) -> None:
    """Usuwa ofertę; z rankingu/bloga dostaje status „rejected”, by odczyt jej nie przywrócił
    (oficjalne obligacje wracają przy następnym odczycie). Oferta z bloga, której nikt jeszcze nie
    ocenił, liczy się w pomiarze trafności jako odrzucona."""
    conn.execute(
        "UPDATE invest_offer SET archived_at = ?, "
        "status = CASE WHEN source IN ('ranking', 'blog') THEN 'rejected' ELSE status END, "
        "verdict = CASE WHEN extracted IS NOT NULL AND verdict IS NULL THEN 'rejected' "
        "ELSE verdict END "
        "WHERE id = ?",
        (now_iso(), offer_id),
    )


def _same(a: object, b: object) -> bool:
    return Decimal(str(a or 0)) == Decimal(str(b or 0))


def confirm_offer(
    conn: sqlite3.Connection,
    offer_id: int,
    bank: str = "",
    fields: dict[str, str] | None = None,
) -> None:
    """Potwierdza ofertę „do sprawdzenia” (z poprawioną nazwą banku i, dla ofert z bloga, polami
    stawka / limit / okres / warunki). Porównanie z tym, co wyciągnął model, daje werdykt
    `clean` albo `fixed` (pomiar trafności)."""
    name = " ".join(bank.split())[:40]
    row = conn.execute(
        "SELECT * FROM invest_offer WHERE id = ? AND archived_at IS NULL", (offer_id,)
    ).fetchone()
    if row is None:
        return
    sets: dict[str, object] = {"status": "confirmed"}
    if name:
        sets["bank"] = name
    if fields is not None:
        pct, cap, months, cond = _offer_fields(
            row["kind"],
            fields.get("rate"),
            fields.get("limit_amount"),
            fields.get("months"),
            fields.get("conditions", ""),
        )
        sets.update(
            rate=str(pct),
            limit_amount=None if cap is None else str(cap),
            months=months,
            conditions=cond,
        )
    if row["extracted"] and row["verdict"] is None:
        was = json.loads(row["extracted"])
        same = (
            _same(was.get("rate"), sets.get("rate", row["rate"]))
            and _same(was.get("limit_amount"), sets.get("limit_amount", row["limit_amount"]))
            and _same(was.get("months"), sets.get("months", row["months"]))
            and was.get("bank") == sets.get("bank", row["bank"])
        )
        sets["verdict"] = "clean" if same else "fixed"
    conn.execute(
        f"UPDATE invest_offer SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?",
        (*sets.values(), offer_id),
    )


def blog_accuracy(conn: sqlite3.Connection) -> tuple[int, int]:
    """(oferty z bloga potwierdzone bez poprawek, wszystkie ocenione) — cel M22 E3: ≥ 8 z 10."""
    row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(verdict = 'clean'), 0) AS ok FROM invest_offer "
        "WHERE source = 'blog' AND verdict IS NOT NULL"
    ).fetchone()
    return int(row["ok"]), int(row["n"])


# --- banki użytkownika (filtr ofert „tylko dla nowych klientów”) ----------------------------


def all_banks(conn: sqlite3.Connection) -> list[Bank]:
    return [
        Bank(r["id"], r["name"]) for r in conn.execute("SELECT * FROM invest_bank ORDER BY name")
    ]


def is_client(clients: Sequence[str], bank: str) -> bool:
    """Czy `bank` to bank użytkownika (bez wielkości liter; „ING” pasuje do „ING Bank Śląski”)."""
    mine = bank.casefold()
    for name in clients:
        short, long = sorted((name.casefold(), mine), key=len)
        if len(short) >= 3 and re.search(rf"(?<!\w){re.escape(short)}(?!\w)", long):
            return True
    return False


def is_hidden(offer: Offer, clients: Sequence[str]) -> bool:
    """Oferta „tylko dla nowych” z banku, w którym użytkownik już jest klientem."""
    return offer.new_only and is_client(clients, offer.bank)


def save_bank(conn: sqlite3.Connection, name: str) -> None:
    clean = " ".join(name.split())[:40]
    if not clean:
        raise InvestError("Podaj nazwę banku.")
    if any(b.name.casefold() == clean.casefold() for b in all_banks(conn)):
        raise InvestError("Ten bank już jest na liście.")
    conn.execute("INSERT INTO invest_bank (name, created_at) VALUES (?, ?)", (clean, now_iso()))


def delete_bank(conn: sqlite3.Connection, bank_id: int) -> None:
    conn.execute("DELETE FROM invest_bank WHERE id = ?", (bank_id,))
