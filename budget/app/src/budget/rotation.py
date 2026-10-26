"""Rekomendacja „dokąd przelać” (M32 E4): zostań na Velobanku vs przelej na konto oszczędnościowe.

Tylko liczy i podpowiada — Budżet niczego nie przelewa. Stopy Velobanku pochodzą z monitora
regulaminu (`promo_watch_velo.rates`; None = wstrzymana, wtedy brak rekomendacji), saldo z księgi
kont banku Velobank, konta docelowe z `savings`. Pieniądze jako `Decimal`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from budget import ledger, money, promo_watch_velo, savings

WINDOW_DAYS = 14  # rekomendacja w tylu ostatnich dniach promocji
THRESHOLDS = (14, 7, 2)  # progi powiadomień, jak w E2
MIN_GAIN = Decimal(1)  # zysk netto poniżej tej kwoty (zł) nie jest wart przelewu
DEFAULT_HORIZON = 30  # dni, gdy konto docelowe nie ma przyszłego końca promocji
VELO_BANK = "%velo%"  # nazwa banku (ASPSP z Enable Banking) na koncie w księdze, bez wielkości
BALANCE_TYPES = ("ITAV", "ITBD", "CLAV", "CLBD")  # preferowane typy salda


@dataclass(frozen=True)
class Recommendation:
    amount: Decimal  # ile przelać (zł)
    account: str  # nazwa konta docelowego
    gain: Decimal  # zysk netto względem pozostania na Velobanku (zł)
    days_left: int  # dni do końca promocji Velobanku
    ends_by: date
    rate: Decimal  # stopa efektywna konta docelowego (% rocznie)
    base_rate: Decimal  # stopa bazowa Velobanku po promocji
    horizon: int  # dni, za które policzono zysk

    @property
    def text(self) -> str:
        return (
            f"Promocja Velobanku kończy się {self.ends_by:%d.%m}. "
            f"Przelej {money.pl(self.amount, 'PLN')}"
            f" na {self.account} ({money.pl(self.rate)}% zamiast {money.pl(self.base_rate)}%) — "
            f"zysk netto ok. {money.pl(self.gain, 'PLN')} w {self.horizon} dni. "
            "Przelej sam — Budżet nie przelewa."
        )


def velo_balance(conn: sqlite3.Connection) -> Decimal:
    """Saldo oszczędnościowych kont Velobanku z ostatnich migawek; ZERO bez salda.

    Tylko `savings`: ROR z wpływami to środki na bieżące wydatki, nie do przelania.
    """
    total = money.ZERO
    rows = conn.execute(
        "SELECT id FROM account WHERE bank LIKE ? AND kind = 'savings'", (VELO_BANK,)
    ).fetchall()
    for row in rows:
        snaps = ledger.latest_balances(conn, row["id"])
        kind = next((t for t in BALANCE_TYPES if t in snaps), None)
        if kind is not None:
            total += Decimal(snaps[kind]["amount"])
    return total


def _rate(value: float) -> Decimal:
    return Decimal(str(value))


def _candidate(
    acc: savings.Account, balance: Decimal, offer: promo_watch_velo.Offer, today: date
) -> Recommendation | None:
    ends = offer.ends_by()
    base = _rate(offer.base_rate)
    promo = acc.promo_days_left(ends) is not None  # czy stopa promocyjna dotrwa do przelewu
    rate = acc.promo_rate if promo else acc.base_rate
    if rate is None or rate <= base:
        return None
    amount = balance
    if promo and acc.promo_limit:
        amount = min(amount, acc.promo_limit)
    amount = amount.quantize(money.CENT)
    if amount <= 0:
        return None
    horizon = DEFAULT_HORIZON
    if promo and acc.promo_until is not None and acc.promo_until > ends:
        horizon = (acc.promo_until - ends).days
    gross = amount * (rate - base) / 100 / 365 * horizon
    gain = savings.net(gross)
    if gain < MIN_GAIN:
        return None
    return Recommendation(amount, acc.name, gain, (ends - today).days, ends, rate, base, horizon)


def recommend(conn: sqlite3.Connection, today: date) -> Recommendation | None:
    """Najlepsze konto docelowe w ostatnich 14 dniach promocji Velobanku; None, gdy edycja
    wstrzymana, poza oknem, brak salda albo zysk < 1 zł."""
    offer = promo_watch_velo.rates(conn)
    if offer is None:
        return None
    if not 0 <= (offer.ends_by() - today).days <= WINDOW_DAYS:
        return None
    balance = velo_balance(conn)
    if balance <= 0:
        return None
    found = (_candidate(a, balance, offer, today) for a in savings.all_accounts(conn))
    best = [r for r in found if r is not None]
    return max(best, key=lambda r: r.gain, default=None)
