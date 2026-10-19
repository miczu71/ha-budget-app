"""Uzasadnienie rekomendacji agenta inwestycyjnego (M22 E4): 2–3 zdania od modelu.

Liczy silnik (`invest.advice`); model tylko opisuje jego wynik. Do modelu idą wyłącznie kwoty
zbiorcze i rodzaje opcji — bez nazw kont, kredytów i banków (decyzje 12/23). Tekst jest zapisany
w `kv` razem z odciskiem wejścia: ekran i push pokazują go tylko wtedy, gdy wciąż pasuje do
rekomendacji, a odświeżenie (raz dziennie, `Service.watch_invest_why`) woła model tylko po zmianie.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from typing import Any

from budget import invest
from budget.invest_blogs import USAGE_KEY
from budget.settings import Settings
from budget.storage import db
from budget.suggest import client
from budget.suggest import engine as suggest
from budget.suggest.client import AIError

log = logging.getLogger(__name__)

KEY = "invest_why"
SCHEMA_NAME = "uzasadnienie_rekomendacji"
MAX_CHARS = 600
RESERVE = 1  # jedno wywołanie ponad limit blogów, żeby wpisy nie zagłodziły uzasadnienia
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


def facts(adv: invest.Advice) -> dict[str, Any] | None:
    """Wejście dla modelu; None, gdy nie ma czego uzasadniać (brak nadwyżki albo danych)."""
    rec = adv.rec
    if rec.state != "invest" or rec.surplus is None:
        return None
    cushion = adv.buckets[0]
    return {
        "nadwyzka_miesieczna_zl": int(rec.surplus),
        "poduszka_cel_zl": int(cushion.target or 0),
        "poduszka_stan_zl": int(cushion.have),
        "podzial": [
            {
                "koszyk": invest.BUCKET_NAMES.get(p.bucket, "cele"),
                "kwota_zl": int(p.amount),
                "opcja": invest.OPTION_KINDS.get(p.option.key, "oferta")
                if p.option
                else "brak pasującej opcji",
                "zysk_netto_zl_rocznie": int(p.option.per_year) if p.option else 0,
            }
            for p in rec.parts
        ],
    }


def fingerprint(data: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def build_prompt(data: dict[str, Any]) -> str:
    return (
        "Jesteś doradcą domowego budżetu. Poniżej wynik obliczeń: ile można odkładać co miesiąc "
        "i gdzie. Napisz po polsku 2–3 krótkie zdania uzasadnienia: dlaczego najpierw poduszka, "
        "a reszta na długi termin, i co daje wybrana opcja. Używaj wyłącznie podanych liczb, "
        "niczego nie wymyślaj, nie obiecuj zysków, nie dawaj innych rekomendacji. "
        'Zwróć JSON {"text": "..."}.\n\n' + json.dumps(data, ensure_ascii=False)
    )


def text(conn: sqlite3.Connection, adv: invest.Advice) -> str | None:
    """Zapisane uzasadnienie, o ile dotyczy dzisiejszej rekomendacji."""
    data = facts(adv)
    raw = db.kv_get(conn, KEY)
    if data is None or not raw or raw.get("key") != fingerprint(data):
        return None
    return str(raw["text"]) or None


async def refresh(
    conn: sqlite3.Connection,
    settings: Settings,
    adv: invest.Advice,
    now: datetime,
    call: suggest.Call = client.complete,
) -> None:
    """Nowe uzasadnienie po zmianie rekomendacji; nigdy nie rzuca. Wspólny dzienny limit
    `invest_daily_calls` z blogami."""
    data = facts(adv)
    if data is None or not settings.ai_enabled or settings.invest_daily_calls <= 0:
        return
    key = fingerprint(data)
    if (db.kv_get(conn, KEY) or {}).get("key") == key:
        return
    today = now.date()
    used = int(suggest.usage(conn, today, USAGE_KEY).get("calls", 0))
    if used >= settings.invest_daily_calls + RESERVE:
        return
    try:
        result = await suggest.metered_call(
            conn,
            settings,
            today,
            call,
            key=USAGE_KEY,
            prompt=build_prompt(data),
            schema=SCHEMA,
            schema_name=SCHEMA_NAME,
        )
    except AIError as exc:
        log.warning("Uzasadnienie rekomendacji nieudane: %s", exc)
        return
    body = " ".join(str(result.get("text", "")).split())[:MAX_CHARS]
    if body:
        db.kv_set(conn, KEY, {"key": key, "text": body})
