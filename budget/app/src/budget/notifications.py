"""Powiadomienia operacyjne (SPEC §6.2): zgoda wygasa, sesja nieaktywna, synchronizacje zawodzą.

Każdy alert to `persistent_notification` (stały identyfikator — HA podmienia, nie mnoży)
oraz opcjonalnie wiadomość przez `notify_service`. Aktywny alert jest ponawiany najwyżej raz
na `RESEND_AFTER`; alert, który ustał, jest zamykany (dismiss).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from budget.ha_client import HAClient, HAError
from budget.sessions import SessionRecord
from budget.storage.db import kv_get, kv_set

log = logging.getLogger(__name__)

STATE_KEY = "notify_state"
RESEND_AFTER = timedelta(hours=24)
TITLE = "Budżet Domowy"


@dataclass(frozen=True)
class Alert:
    key: str
    message: str


def evaluate(
    record: SessionRecord | None,
    *,
    failures: int,
    manual_sync_needed: bool,
    warning_days: int,
    now: datetime,
    failures_to_alert: int = 3,
) -> list[Alert]:
    alerts = []
    if record is not None and not record.active:
        alerts.append(
            Alert(
                "session_inactive",
                f"Zgoda bankowa nieaktywna ({record.status}). Synchronizacja wstrzymana — "
                "odnów zgodę w panelu (Bank → Odnów zgodę).",
            )
        )
    elif record is not None and record.days_left(now) <= warning_days:
        alerts.append(
            Alert(
                "consent_expiring",
                f"Zgoda bankowa wygasa za {record.days_left(now)} dni "
                f"({record.valid_until:%Y-%m-%d}). Odnów ją w panelu (Bank → Odnów zgodę).",
            )
        )
    if failures >= failures_to_alert:
        alerts.append(
            Alert(
                "sync_failures",
                f"{failures} nieudane synchronizacje z rzędu — szczegóły na ekranie Status.",
            )
        )
    if manual_sync_needed:
        alerts.append(
            Alert(
                "manual_sync",
                "Okno transakcji nie zmieściło się w dziennym limicie zapytań banku. "
                "Uruchom „Synchronizuj teraz” w panelu (z panelu limit nie obowiązuje).",
            )
        )
    return alerts


class Notifier:
    def __init__(
        self, ha: HAClient, *, notify_service: str | None, panel_url: str | None = None
    ) -> None:
        self._ha = ha
        self._notify_service = notify_service
        self.panel_url = panel_url

    async def process(self, conn: sqlite3.Connection, alerts: list[Alert], now: datetime) -> None:
        state: dict[str, str] = kv_get(conn, STATE_KEY) or {}
        active = {a.key for a in alerts}
        for alert in alerts:
            last = state.get(alert.key)
            if last and now - datetime.fromisoformat(last) < RESEND_AFTER:
                continue
            if await self._send(alert):
                state[alert.key] = now.isoformat()
        for key in [k for k in state if k not in active]:
            try:
                await self._ha.dismiss_notification(f"budget_{key}")
            except HAError as exc:
                log.warning("Nie udało się zamknąć powiadomienia %s: %s", key, exc)
            del state[key]
        kv_set(conn, STATE_KEY, state or None)

    async def _send(self, alert: Alert) -> bool:
        message = alert.message
        if self.panel_url:
            message += f"\n\n[Otwórz panel Budżetu]({self.panel_url})"
        sent = False
        try:
            await self._ha.persistent_notification(f"budget_{alert.key}", TITLE, message)
            sent = True
        except HAError as exc:
            log.warning("persistent_notification (%s) nie wysłane: %s", alert.key, exc)
        if self._notify_service:
            try:
                await self._ha.notify(self._notify_service, TITLE, alert.message)
                sent = True
            except HAError as exc:
                log.warning("%s (%s) nie wysłane: %s", self._notify_service, alert.key, exc)
        if sent:
            log.info("Powiadomienie: %s", alert.key)
        return sent
