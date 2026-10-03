"""Reguły użytkownika: warunki (AND) → podkategoria i opcjonalnie nazwa sprzedawcy.

Wygrywa pierwsza pasująca reguła wg `priority` rosnąco (lista w panelu od góry). Nowa reguła
trafia na górę — świeża decyzja użytkownika ma pierwszeństwo przed starszymi, ogólniejszymi.
Teksty porównywane po `fold` (wielkie litery, bez polskich znaków); konto kontrahenta bez spacji.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any

from budget.normalize import fold
from budget.storage.db import now_iso

TEXT_FIELDS = {
    "merchant": "sprzedawca / odbiorca",
    "description": "opis / tytuł",
    "counterparty_name": "kontrahent",
    "counterparty_account": "konto kontrahenta",
}
OPS = {"contains": "zawiera", "equals": "równa się", "starts_with": "zaczyna się od"}
DIRECTIONS = {"out": "wydatek", "in": "wpływ"}
MAX_TEXT_CONDITIONS = 3
VALUE_MAX = 120
RENAME_MAX = 60


class RuleError(ValueError):
    """Komunikat dla użytkownika panelu."""


@dataclass(frozen=True)
class Facts:
    """Pola transakcji, które widzą reguły."""

    account_id: int
    kind: str
    amount: Decimal
    merchant: str
    description: str
    counterparty_name: str
    counterparty_account: str


@lru_cache(maxsize=100_000)
def _norm(name: str, value: str | None) -> str:
    if name == "counterparty_account":
        return re.sub(r"\s+", "", value or "").upper()
    return fold(value)


@dataclass(frozen=True)
class TextCondition:
    field: str
    op: str
    value: str

    def matches(self, facts: Facts) -> bool:
        return self.matches_text(getattr(facts, self.field))

    def matches_text(self, value: str | None) -> bool:
        """Dopasowanie samej wartości pola (np. nazwy sprzedawcy grupy w kolejce)."""
        have = _norm(self.field, value)
        want = _norm(self.field, self.value)
        if self.op == "equals":
            return have == want
        if self.op == "starts_with":
            return have.startswith(want)
        return want in have


@dataclass(frozen=True)
class Conditions:
    text: tuple[TextCondition, ...] = ()
    account_id: int | None = None
    kind: str | None = None
    direction: str | None = None
    amount_min: Decimal | None = None  # wartość bezwzględna
    amount_max: Decimal | None = None

    def matches(self, facts: Facts) -> bool:
        if self.account_id is not None and facts.account_id != self.account_id:
            return False
        if self.kind is not None and facts.kind != self.kind:
            return False
        if self.direction == "out" and facts.amount >= 0:
            return False
        if self.direction == "in" and facts.amount <= 0:
            return False
        size = abs(facts.amount)
        if self.amount_min is not None and size < self.amount_min:
            return False
        if self.amount_max is not None and size > self.amount_max:
            return False
        return all(c.matches(facts) for c in self.text)

    def to_json(self) -> str:
        data: dict[str, Any] = {"text": [vars(c) for c in self.text]}
        for key in ("account_id", "kind", "direction"):
            if (value := getattr(self, key)) is not None:
                data[key] = value
        for key in ("amount_min", "amount_max"):
            if (value := getattr(self, key)) is not None:
                data[key] = str(value)
        return json.dumps(data, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> Conditions:
        data = json.loads(text)
        return cls(
            text=tuple(TextCondition(**c) for c in data.get("text", [])),
            account_id=data.get("account_id"),
            kind=data.get("kind"),
            direction=data.get("direction"),
            amount_min=Decimal(data["amount_min"]) if "amount_min" in data else None,
            amount_max=Decimal(data["amount_max"]) if "amount_max" in data else None,
        )


@dataclass(frozen=True)
class Rule:
    id: int | None
    category_id: int
    conditions: Conditions = field(default_factory=Conditions)
    rename: str | None = None
    enabled: bool = True
    priority: int = 0
    hits: int = 0

    def matches(self, facts: Facts) -> bool:
        return self.enabled and self.conditions.matches(facts)


def _row(r: sqlite3.Row) -> Rule:
    return Rule(
        id=int(r["id"]),
        category_id=int(r["category_id"]),
        conditions=Conditions.from_json(r["conditions"]),
        rename=r["rename"],
        enabled=bool(r["enabled"]),
        priority=int(r["priority"]),
        hits=int(r["hits"]),
    )


def all_rules(conn: sqlite3.Connection) -> list[Rule]:
    """W kolejności stosowania."""
    return [_row(r) for r in conn.execute("SELECT * FROM rule ORDER BY priority, id")]


def get(conn: sqlite3.Connection, rule_id: int) -> Rule | None:
    r = conn.execute("SELECT * FROM rule WHERE id = ?", (rule_id,)).fetchone()
    return _row(r) if r else None


def parse_amount(value: str | None) -> Decimal | None:
    value = (value or "").strip().replace(" ", "").replace(",", ".")
    if not value:
        return None
    try:
        amount = abs(Decimal(value))
    except InvalidOperation as exc:
        raise RuleError(f"Niepoprawna kwota: {value}") from exc
    return amount.quantize(Decimal("0.01"))


def validate(conn: sqlite3.Connection, rule: Rule) -> Rule:
    """Sprawdzona i oczyszczona reguła (wyjątek `RuleError` z komunikatem)."""
    cond = rule.conditions
    text = tuple(
        TextCondition(c.field, c.op, re.sub(r"\s+", " ", c.value).strip())
        for c in cond.text
        if c.value.strip()
    )
    if not text:
        raise RuleError("Reguła potrzebuje co najmniej jednego warunku tekstowego.")
    if len(text) > MAX_TEXT_CONDITIONS:
        raise RuleError(f"Najwyżej {MAX_TEXT_CONDITIONS} warunki tekstowe.")
    for c in text:
        if c.field not in TEXT_FIELDS or c.op not in OPS:
            raise RuleError("Nieznane pole albo operator warunku.")
        if len(c.value) > VALUE_MAX:
            raise RuleError(f"Wartość warunku może mieć najwyżej {VALUE_MAX} znaków.")
        if not re.search(r"[A-Z0-9]", _norm(c.field, c.value)):
            raise RuleError("Wartość warunku nie zawiera liter ani cyfr.")
    if cond.direction not in (None, *DIRECTIONS):
        raise RuleError("Nieznany kierunek.")
    if (
        cond.amount_min is not None
        and cond.amount_max is not None
        and cond.amount_min > cond.amount_max
    ):
        raise RuleError("Kwota „od” jest większa niż „do”.")
    if (
        cond.account_id is not None
        and not conn.execute("SELECT 1 FROM account WHERE id = ?", (cond.account_id,)).fetchone()
    ):
        raise RuleError("Nie ma takiego konta.")
    leaf = conn.execute(
        "SELECT 1 FROM category WHERE id = ? AND parent_id IS NOT NULL", (rule.category_id,)
    ).fetchone()
    if not leaf:
        raise RuleError("Wybierz podkategorię.")
    rename = re.sub(r"\s+", " ", rule.rename or "").strip()[:RENAME_MAX] or None
    return replace(rule, conditions=replace(cond, text=text), rename=rename)


def save(conn: sqlite3.Connection, rule: Rule) -> int:
    """Zapis (nowa reguła na górę listy); zwraca id."""
    rule = validate(conn, rule)
    now = now_iso()
    if rule.id is None:
        top = conn.execute("SELECT min(priority) FROM rule").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO rule (priority, enabled, conditions, category_id, rename, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                (top if top is not None else 0) - 10,
                int(rule.enabled),
                rule.conditions.to_json(),
                rule.category_id,
                rule.rename,
                now,
                now,
            ),
        )
        return int(cur.lastrowid or 0)
    cur = conn.execute(
        "UPDATE rule SET enabled = ?, conditions = ?, category_id = ?, rename = ?, "
        "updated_at = ? WHERE id = ?",
        (
            int(rule.enabled),
            rule.conditions.to_json(),
            rule.category_id,
            rule.rename,
            now,
            rule.id,
        ),
    )
    if not cur.rowcount:
        raise RuleError("Nie ma takiej reguły.")
    return rule.id


def delete(conn: sqlite3.Connection, rule_id: int) -> None:
    conn.execute("DELETE FROM rule WHERE id = ?", (rule_id,))


def set_enabled(conn: sqlite3.Connection, rule_id: int, enabled: bool) -> None:
    conn.execute(
        "UPDATE rule SET enabled = ?, updated_at = ? WHERE id = ?",
        (int(enabled), now_iso(), rule_id),
    )


def move(conn: sqlite3.Connection, rule_id: int, step: int) -> None:
    """Przesunięcie o jedną pozycję (−1 w górę, +1 w dół); priorytety numerowane od nowa."""
    ids = [r.id for r in all_rules(conn)]
    if rule_id not in ids:
        raise RuleError("Nie ma takiej reguły.")
    i = ids.index(rule_id)
    j = min(max(i + step, 0), len(ids) - 1)
    ids[i], ids[j] = ids[j], ids[i]
    for n, rid in enumerate(ids):
        conn.execute("UPDATE rule SET priority = ? WHERE id = ?", ((n + 1) * 10, rid))
