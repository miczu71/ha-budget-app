"""Kredyt hipoteczny wpisany ręcznie (M9 E1, decyzja 28).

Stan = kapitał na dzień + stopa (stawka referencyjna + marża). Harmonogram liczy add-on przy stałej
bieżącej stopie: odsetki za okres = kapitał × stopa × dni / 365, rata równa z wzoru annuitetowego
(stopa / 12), rata malejąca = stała część kapitału. Ostatnia rata domyka saldo. Bank liczy co do
grosza inaczej — stąd ręczna korekta kapitału i stopy.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from budget import money
from budget.recurring import series as S
from budget.storage.db import now_iso

ZERO = money.ZERO
KINDS = {"equal": "równe", "decreasing": "malejące"}
DRIFT = Decimal("0.01")  # rata w księdze różna od harmonogramu o więcej niż 1% → dzwonek
DRIFT_DAYS = 7  # rata z księgi należy do wiersza harmonogramu najwyżej tyle dni od jego dnia


class LoanError(ValueError):
    pass


@dataclass(frozen=True)
class Loan:
    id: int
    name: str
    principal: Decimal
    principal_date: date
    reference_rate: Decimal  # % rocznie
    margin: Decimal  # % rocznie
    installment_kind: str  # "equal" | "decreasing"
    last_payment_date: date
    payment_day: int
    series_id: int | None = None

    @property
    def rate(self) -> Decimal:
        return self.reference_rate + self.margin


@dataclass(frozen=True)
class Installment:
    day: date
    interest: Decimal
    principal: Decimal
    balance: Decimal  # kapitał po racie

    @property
    def payment(self) -> Decimal:
        return self.interest + self.principal


@dataclass(frozen=True)
class Summary:
    principal: Decimal  # kapitał na dziś wg harmonogramu (po ostatniej racie do dziś)
    installment: Decimal  # najbliższa rata
    count: int
    payoff: date | None
    interest_left: Decimal


def _row(r: sqlite3.Row) -> Loan:
    return Loan(
        id=r["id"],
        name=r["name"],
        principal=Decimal(r["principal"]),
        principal_date=date.fromisoformat(r["principal_date"]),
        reference_rate=Decimal(r["reference_rate"]),
        margin=Decimal(r["margin"]),
        installment_kind=r["installment_kind"],
        last_payment_date=date.fromisoformat(r["last_payment_date"]),
        payment_day=r["payment_day"],
        series_id=r["series_id"],
    )


def all_loans(conn: sqlite3.Connection) -> list[Loan]:
    return [
        _row(r) for r in conn.execute("SELECT * FROM loan WHERE archived_at IS NULL ORDER BY name")
    ]


def get(conn: sqlite3.Connection, loan_id: int) -> Loan:
    row = conn.execute("SELECT * FROM loan WHERE id = ?", (loan_id,)).fetchone()
    if row is None:
        raise LoanError("Nie ma takiego kredytu.")
    return _row(row)


def _date(value: str | None, message: str) -> date:
    try:
        return date.fromisoformat(value or "")
    except ValueError as exc:
        raise LoanError(message) from exc


def _percent(value: str | None, what: str, *, allow_negative: bool = False) -> Decimal:
    """Stopa roczna w procentach, np. 5,8 albo 1,7; WIBOR/WIRON może być ujemny tylko jawnie."""
    try:
        rate = money.parse(value)
    except money.AmountError:
        rate = None
    low = Decimal(-10) if allow_negative else ZERO
    if rate is None or rate < low or rate > 50:
        raise LoanError(f"Podaj {what} w procentach, np. 5,8 albo 1,7.")
    return rate


def save(
    conn: sqlite3.Connection,
    *,
    loan_id: int | None,
    name: str,
    principal: str | None,
    principal_date: str | None,
    reference_rate: str | None,
    margin: str | None,
    installment_kind: str,
    last_payment_date: str | None,
    payment_day: str | None,
) -> int:
    """Nowy kredyt (`loan_id` None) albo zmiana; nowy kapitał na nowy dzień to korekta."""
    clean = " ".join(name.split())[:40]
    if not clean:
        raise LoanError("Podaj nazwę kredytu.")
    try:
        capital = money.parse(principal)
    except money.AmountError:
        capital = None
    if capital is None or capital <= ZERO:
        raise LoanError("Podaj kapitał do spłaty większy od zera.")
    start = _date(principal_date, "Podaj datę, na którą jest podany kapitał.")
    end = _date(last_payment_date, "Podaj datę ostatniej raty.")
    if end <= start:
        raise LoanError("Data ostatniej raty musi być po dacie kapitału.")
    if installment_kind not in KINDS:
        raise LoanError("Wybierz rodzaj rat: równe albo malejące.")
    try:
        day = int(payment_day or "")
    except ValueError:
        day = 0
    if not 1 <= day <= 31:
        raise LoanError("Podaj dzień raty (1–31).")
    values = (
        clean,
        str(capital),
        start.isoformat(),
        str(_percent(reference_rate, "stawkę WIBOR/WIRON", allow_negative=True)),
        str(_percent(margin, "marżę")),
        installment_kind,
        end.isoformat(),
        day,
    )
    try:
        if loan_id is None:
            return conn.execute(
                "INSERT INTO loan (name, principal, principal_date, reference_rate, margin,"
                " installment_kind, last_payment_date, payment_day, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*values, now_iso()),
            ).lastrowid  # type: ignore[return-value]
        get(conn, loan_id)
        conn.execute(
            "UPDATE loan SET name = ?, principal = ?, principal_date = ?, reference_rate = ?,"
            " margin = ?, installment_kind = ?, last_payment_date = ?, payment_day = ?"
            " WHERE id = ?",
            (*values, loan_id),
        )
        return loan_id
    except sqlite3.IntegrityError as exc:
        raise LoanError("Kredyt o tej nazwie już jest.") from exc


def archive(conn: sqlite3.Connection, loan_id: int) -> None:
    get(conn, loan_id)
    conn.execute("UPDATE loan SET archived_at = ? WHERE id = ?", (now_iso(), loan_id))


def payment_dates(after: date, last: date, payment_day: int) -> list[date]:
    """Dni rat po `after` (bez tego dnia) do miesiąca `last` włącznie; dzień raty przycięty do
    długości miesiąca (31 → 28/29/30)."""
    out: list[date] = []
    y, m = after.year, after.month
    while (y, m) <= (last.year, last.month):
        d = date(y, m, min(payment_day, calendar.monthrange(y, m)[1]))
        if d > after:
            out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _annuity(principal: Decimal, rate: Decimal, n: int) -> Decimal:
    """Rata równa: P·r / (1 − (1+r)^−n), r = stopa/12 (przy stopie 0 po prostu P/n)."""
    r = rate / 100 / 12
    if r == 0:
        return (principal / n).quantize(money.CENT, ROUND_HALF_UP)
    return (principal * r / (1 - (1 + r) ** -n)).quantize(money.CENT, ROUND_HALF_UP)


def schedule(loan: Loan) -> list[Installment]:
    """Harmonogram od dnia kapitału: raty po `principal_date` do `last_payment_date`."""
    days = payment_dates(loan.principal_date, loan.last_payment_date, loan.payment_day)
    if not days:
        return []
    n, rate, balance = len(days), loan.rate, loan.principal
    level = _annuity(balance, rate, n) if loan.installment_kind == "equal" else ZERO
    part = (loan.principal / n).quantize(money.CENT, ROUND_HALF_UP)
    out: list[Installment] = []
    prev = loan.principal_date
    for i, day in enumerate(days):
        interest = (balance * rate / 100 * (day - prev).days / 365).quantize(
            money.CENT, ROUND_HALF_UP
        )
        if i == n - 1:
            principal = balance
        elif loan.installment_kind == "equal":
            principal = min(balance, max(level - interest, ZERO))
        else:
            principal = min(balance, part)
        balance -= principal
        out.append(Installment(day, interest, principal, balance))
        prev = day
    return out


def summary(lo: Loan, rows: list[Installment], today: date) -> Summary:
    """Stan na `today`: kapitał po ostatniej racie do dziś, reszta z rat przed nami."""
    elapsed = [r for r in rows if r.day <= today]
    left = rows[len(elapsed) :]
    return Summary(
        principal=elapsed[-1].balance if elapsed else lo.principal,
        installment=left[0].payment if left else ZERO,
        count=len(left),
        payoff=rows[-1].day if rows else None,
        interest_left=sum((r.interest for r in left), ZERO),
    )


@dataclass(frozen=True)
class Drift:
    day: date  # dzień raty z księgi
    paid: Decimal
    expected: Decimal  # rata z harmonogramu najbliższa temu dniowi


def drift(rows: list[Installment], paid_day: date, paid: Decimal) -> Drift | None:
    """Rata z księgi vs harmonogram: różnica powyżej `DRIFT` zwykle znaczy zmianę stopy (WIBOR)."""
    near = min(rows, key=lambda r: abs((r.day - paid_day).days), default=None)
    if near is None or abs((near.day - paid_day).days) > DRIFT_DAYS or near.payment == ZERO:
        return None
    if abs(paid - near.payment) / near.payment <= DRIFT:
        return None
    return Drift(paid_day, paid, near.payment)


def set_series(conn: sqlite3.Connection, loan_id: int, series_id: int | None) -> None:
    """Seria rat w księdze (tylko wydatkowa); `None` odpina."""
    get(conn, loan_id)
    if series_id is not None and S.get(conn, series_id).direction != "out":
        raise LoanError("Rata kredytu to seria wydatkowa.")
    conn.execute("UPDATE loan SET series_id = ? WHERE id = ?", (series_id, loan_id))
