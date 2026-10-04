"""Pola warunków reguły wspólne dla edytora Reguł i kolejki „Do przejrzenia”.

Formularz: `field_i` / `op_i` / `value_i` (do `rules.MAX_TEXT_CONDITIONS` warunków tekstowych),
`account_id`, `kind`, `direction`, `amount_min`, `amount_max`, `rename`; szablon
`_rule_conditions.html` renderuje je z kontekstu `conditions_context`. `prefix` — gdy formularz ma
własne pola o tych nazwach (grupa kolejki: `kind`, `direction`), np. `rule_kind`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from typing import Any

from starlette.datastructures import FormData

from budget.categorize import rules
from budget.categorize.rules import Conditions, Rule, RuleError, TextCondition
from budget.normalize import fold

RULE = "rule_"  # prefiks pól reguły w formularzach kategorii (kolejka ma własne `kind`/`direction`)
MIN_FRAGMENT = 3  # znaki (bez ogonków) w tekście warunku „zawiera” / „zaczyna się od”


def _int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def has_text(form: FormData, prefix: str = "") -> bool:
    """Czy formularz niesie choć jeden warunek tekstowy."""
    return any(
        str(form.get(f"{prefix}value_{i}") or "").strip() for i in range(rules.MAX_TEXT_CONDITIONS)
    )


def rule_from_form(form: FormData, prefix: str = "") -> Rule:
    """Pola formularza → reguła (walidacja w `rules.validate`; `RuleError` przy złej kwocie)."""
    text = []
    for i in range(rules.MAX_TEXT_CONDITIONS):
        value = str(form.get(f"{prefix}value_{i}") or "")
        if value.strip():
            text.append(
                TextCondition(
                    str(form.get(f"{prefix}field_{i}") or "merchant"),
                    str(form.get(f"{prefix}op_{i}") or "contains"),
                    value,
                )
            )
    category = _int(form.get("category_id"))
    return Rule(
        id=_int(form.get("id")),
        category_id=category if category is not None else 0,
        conditions=Conditions(
            text=tuple(text),
            account_id=_int(form.get(f"{prefix}account_id")),
            kind=str(form.get(f"{prefix}kind") or "") or None,
            direction=str(form.get(f"{prefix}direction") or "") or None,
            amount_min=rules.parse_amount(str(form.get(f"{prefix}amount_min") or "")),
            amount_max=rules.parse_amount(str(form.get(f"{prefix}amount_max") or "")),
        ),
        rename=str(form.get(f"{prefix}rename") or "") or None,
        enabled=form.get("enabled") is not None or form.get("id") is None,
    )


def requested(form: FormData | None) -> bool:
    """Reguła tylko na żądanie („utwórz regułę”); domyślnie kategoria ręczna."""
    return form is not None and form.get("make_rule") is not None


def form_rule(form: FormData | None, default: Rule, prefix: str = RULE) -> Rule:
    """Reguła z pól formularza kategorii (bez kategorii i walidacji). Bez warunków tekstowych
    (np. formularz bez bloku reguły) → `default`; pole kierunku niewysłane (nie: „oba”) →
    kierunek z `default`."""
    if form is None or not has_text(form, prefix):
        return default
    rule = replace(rule_from_form(form, prefix), id=None, enabled=True)
    if f"{prefix}direction" not in form:
        rule = replace(
            rule, conditions=replace(rule.conditions, direction=default.conditions.direction)
        )
    return rule


def check_fragments(cond: Conditions) -> None:
    """Fragment tekstu w „zawiera” / „zaczyna się od” nie może być za krótki."""
    for c in cond.text:
        if c.op != "equals" and len(fold(c.value)) < MIN_FRAGMENT:
            raise RuleError(f"Tekst reguły musi mieć co najmniej {MIN_FRAGMENT} znaki.")


def accounts(conn: sqlite3.Connection) -> dict[int, str]:
    return {
        int(a["id"]): a["display_name"] or a["product"] or f"#{a['id']}"
        for a in conn.execute("SELECT * FROM account ORDER BY id")
    }


def describe(rule: Rule, names: dict[int, str]) -> str:
    """Warunki reguły jednym zdaniem (lista reguł, podgląd w kolejce)."""
    c = rule.conditions
    parts = [f"{rules.TEXT_FIELDS[t.field]} {rules.OPS[t.op]} „{t.value}”" for t in c.text]
    if c.account_id is not None:
        parts.append(f"konto {names.get(c.account_id, '#' + str(c.account_id))}")
    if c.kind:
        parts.append(f"typ {c.kind}")
    if c.direction:
        parts.append(rules.DIRECTIONS[c.direction])
    if c.amount_min is not None:
        parts.append(f"kwota ≥ {c.amount_min}")
    if c.amount_max is not None:
        parts.append(f"kwota ≤ {c.amount_max}")
    return " i ".join(parts)


def conditions_context(conn: sqlite3.Connection, rule: Rule, prefix: str = "") -> dict[str, Any]:
    """Kontekst `_rule_conditions.html`: reguła (`crule`) i komplet wierszy warunków tekstowych."""
    text = list(rule.conditions.text)
    # puste wiersze: pierwszy na sprzedawcę, kolejne na opis/tytuł (najczęstszy drugi warunek)
    while len(text) < rules.MAX_TEXT_CONDITIONS:
        text.append(TextCondition("description" if text else "merchant", "contains", ""))
    return {
        "crule": rule,
        "px": prefix,
        "text": text,
        "accounts": accounts(conn),
        "kinds": [r[0] for r in conn.execute("SELECT DISTINCT kind FROM txn ORDER BY 1")],
        "fields": rules.TEXT_FIELDS,
        "ops": rules.OPS,
        "directions": rules.DIRECTIONS,
    }
