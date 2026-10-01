"""Modele odpowiedzi Enable Banking API (tylko pola, z których korzystamy — reszta w `raw`).

Kwoty są w API stringami i parsujemy je wyłącznie do `Decimal`; float jest odrzucany.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _no_float(value: Any) -> Any:
    if isinstance(value, float):
        raise ValueError("kwota jako float — oczekiwany string (precyzja Decimal)")
    return value


Money = Annotated[Decimal, BeforeValidator(_no_float)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


class _RawModel(_Model):
    """Model, który zachowuje surowy dict odpowiedzi (do `raw_json` w bazie)."""

    raw: dict[str, Any] = Field(default_factory=dict, exclude=True, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        return cls.model_validate({**data, "raw": data})


class Amount(_Model):
    currency: str
    amount: Money


class Aspsp(_Model):
    name: str
    country: str
    bic: str | None = None
    maximum_consent_validity: int | None = None
    required_psu_headers: list[str] = Field(default_factory=list)
    psu_types: list[str] = Field(default_factory=list)
    beta: bool = False


class AspspRef(_Model):
    name: str
    country: str


class Access(_Model):
    valid_until: datetime
    balances: bool | None = None
    transactions: bool | None = None


class Application(_Model):
    name: str | None = None
    kid: str | None = None
    environment: str | None = None
    redirect_urls: list[str] = Field(default_factory=list)
    active: bool | None = None
    countries: list[str] = Field(default_factory=list)


class AuthResponse(_Model):
    url: str
    authorization_id: str | None = None


class AccountIdentification(_Model):
    iban: str | None = None
    other: dict[str, Any] | None = None


class Account(_RawModel):
    uid: str
    identification_hash: str
    identification_hashes: list[str] = Field(default_factory=list)
    account_id: AccountIdentification | None = None
    name: str | None = None
    product: str | None = None
    currency: str
    cash_account_type: str | None = None

    @property
    def iban(self) -> str | None:
        return self.account_id.iban if self.account_id else None


class SessionResponse(_RawModel):
    """Odpowiedź `POST /sessions` — część danych EB zwraca tylko tu, więc `raw` trzeba zapisać."""

    session_id: str
    accounts: list[Account] = Field(default_factory=list)
    aspsp: AspspRef
    psu_type: str | None = None
    access: Access

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        accounts = [Account.from_api(a) for a in data.get("accounts", [])]
        return cls.model_validate({**data, "accounts": accounts, "raw": data})


class SessionInfo(_RawModel):
    """Odpowiedź `GET /sessions/{id}`."""

    status: str
    access: Access
    accounts: list[str] = Field(default_factory=list)
    aspsp: AspspRef | None = None
    psu_type: str | None = None
    created: datetime | None = None
    authorized: datetime | None = None


class Balance(_RawModel):
    name: str | None = None
    balance_amount: Amount
    balance_type: str
    reference_date: date | None = None
    last_change_date_time: datetime | None = None


class Party(_Model):
    name: str | None = None


class OtherIdentification(_Model):
    identification: str | None = None
    scheme_name: str | None = None


class GenericIdentification(_Model):
    iban: str | None = None
    other: OtherIdentification | None = None

    @property
    def number(self) -> str | None:
        """IBAN albo `other.identification` — Millennium podaje numer kontrahenta jako
        `other` ze schematem BBAN, choć wartość ma postać IBAN (PL + 26 cyfr)."""
        if self.iban:
            return self.iban
        return self.other.identification if self.other else None


class BankTransactionCode(_Model):
    code: str | None = None
    sub_code: str | None = None
    description: str | None = None


class Transaction(_RawModel):
    transaction_id: str | None = None
    entry_reference: str | None = None
    transaction_amount: Amount
    credit_debit_indicator: str
    status: str
    booking_date: date | None = None
    value_date: date | None = None
    transaction_date: date | None = None
    creditor: Party | None = None
    debtor: Party | None = None
    creditor_account: GenericIdentification | None = None
    debtor_account: GenericIdentification | None = None
    remittance_information: list[str] = Field(default_factory=list)
    merchant_category_code: str | None = None
    bank_transaction_code: BankTransactionCode | None = None
    balance_after_transaction: Amount | None = None

    @property
    def is_credit(self) -> bool:
        return self.credit_debit_indicator == "CRDT"

    @property
    def signed_amount(self) -> Decimal:
        """Kwota ze znakiem: + wpływ (CRDT), − wydatek (DBIT)."""
        amount = abs(self.transaction_amount.amount)
        return amount if self.is_credit else -amount

    @property
    def counterparty_name(self) -> str | None:
        party = self.debtor if self.is_credit else self.creditor
        return party.name if party else None

    @property
    def counterparty_iban(self) -> str | None:
        acc = self.debtor_account if self.is_credit else self.creditor_account
        return acc.number if acc else None

    @property
    def description(self) -> str:
        return " ".join(s.strip() for s in self.remittance_information if s and s.strip())


class TransactionsPage(_Model):
    transactions: list[Transaction] = Field(default_factory=list)
    continuation_key: str | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> TransactionsPage:
        return cls(
            transactions=[Transaction.from_api(t) for t in data.get("transactions", [])],
            continuation_key=data.get("continuation_key") or None,
        )
