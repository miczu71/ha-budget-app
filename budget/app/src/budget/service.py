"""Usługa add-onu: synchronizacja (harmonogram i na żądanie), encje MQTT, powiadomienia.

Wszystko działa w jednej pętli asyncio (panel, harmonogram, MQTT) i korzysta z jednego
połączenia SQLite — bez wątków, więc bez blokad bazy. Przebiegi synchronizacji są
serializowane blokadą.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from budget import ha_publisher, inbox, notifications, sessions, sync_service
from budget.eb_client import EBClient, EBError, PsuHeaders
from budget.ha_client import HAClient
from budget.recurring import detect
from budget.settings import Settings, SettingsError, resolve_private_key_path
from budget.snapshot import Snapshot
from budget.suggest import engine as suggest
from budget.sync_service import SyncResult

log = logging.getLogger(__name__)

SESSION_CHECK_EVERY = timedelta(hours=6)
REFRESH_DEBOUNCE = 2.0  # s — seria zapisów w panelu = jedno odświeżenie encji
MIDNIGHT_OFFSET = timedelta(seconds=5)


def next_midnight(now: datetime) -> datetime:
    """Najbliższa północ (+ chwila) w strefie `now` — nowy „na dzień” i nowy miesiąc encji Flex."""
    day = now.date() + timedelta(days=1)
    return datetime.combine(day, time(), tzinfo=now.tzinfo) + MIDNIGHT_OFFSET


class ServiceError(Exception):
    """Komunikat dla użytkownika panelu."""


class Service:
    def __init__(
        self,
        settings: Settings,
        conn: sqlite3.Connection,
        ha: HAClient,
        *,
        tz: ZoneInfo,
        eb_base_url: str | None = None,
    ) -> None:
        self.settings = settings
        self.conn = conn
        self.ha = ha
        self.tz = tz
        self.publisher: ha_publisher.Publisher | None = None
        self.notifier = notifications.Notifier(ha, notify_service=settings.notify_service)
        self.lock = asyncio.Lock()
        self.last_result: SyncResult | None = None
        self.ai_lock = asyncio.Lock()
        self._ai_task: asyncio.Task[None] | None = None
        self._refresh_task: asyncio.Task[None] | None = None
        self.balance_memo = inbox.BalanceMemo()
        self.snapshot = Snapshot(conn)
        self._eb_base_url = eb_base_url or settings.eb_base_url

    # --- Enable Banking ---------------------------------------------------------------------

    def missing_config(self) -> list[str]:
        """Czego brakuje do połączenia z Enable Banking (puste = gotowe)."""
        missing = []
        if not self.settings.eb_application_id:
            missing.append("identyfikator aplikacji (opcja eb_application_id)")
        if not self.settings.private_key_path.is_file():
            missing.append("klucz prywatny (.pem) — wgraj go na ekranie Bank")
        return missing

    def eb_client(self) -> EBClient:
        missing = self.missing_config()
        if missing:
            raise ServiceError("Brak konfiguracji: " + "; ".join(missing))
        try:
            pem = resolve_private_key_path(self.settings).read_bytes()
            return EBClient(self.settings.eb_application_id or "", pem, base_url=self._eb_base_url)
        except (SettingsError, ValueError) as exc:
            raise ServiceError(f"Klucz prywatny nieczytelny: {exc}") from exc

    # --- synchronizacja ---------------------------------------------------------------------

    def now(self) -> datetime:
        return datetime.now(self.tz)

    async def sync(
        self, trigger: str, *, psu: PsuHeaders | None = None, full: bool = False
    ) -> SyncResult:
        async with self.lock, self.eb_client() as eb:
            result = await sync_service.sync(
                self.conn, eb, tz=self.tz, trigger=trigger, psu=psu, full=full
            )
        self.last_result = result
        self.detect_series()
        await self.refresh()
        self.suggest_later()
        return result

    # --- płatności cykliczne (M5b) ------------------------------------------------------------

    def detect_series(self) -> list[detect.Proposal]:
        """Nowe propozycje serii po synchronizacji (lokalnie, ułamek sekundy); błąd nie
        zatrzymuje synchronizacji."""
        try:
            found = detect.run(self.conn, self.now().date())
        except Exception:
            log.exception("Błąd wykrywania płatności cyklicznych")
            return []
        if found:
            log.info("Nowe propozycje płatności cyklicznych: %d", len(found))
        return found

    # --- podpowiedzi AI (M4c) -----------------------------------------------------------------

    async def suggest(self) -> suggest.RunResult:
        """Podpowiedzi dla kolejki (jeden przebieg naraz)."""
        async with self.ai_lock:
            return await suggest.run(self.conn, self.settings, self.now().date())

    async def _suggest_quietly(self) -> None:
        try:
            await self.suggest()
        except Exception:  # podpowiedzi nie mogą zatrzymać add-onu
            log.exception("Nieoczekiwany błąd podpowiedzi AI")

    def suggest_later(self) -> None:
        """Przebieg w tle po synchronizacji — odpowiedź panelu nie czeka na router AI."""
        if not self.settings.ai_enabled or (self._ai_task and not self._ai_task.done()):
            return
        self._ai_task = asyncio.create_task(self._suggest_quietly())

    async def sync_from_button(self) -> None:
        """Przycisk w HA: bez danych użytkownika (PSU), więc w ramach limitu dziennego."""
        try:
            await self.sync("button")
        except ServiceError as exc:
            log.warning("Synchronizacja z przycisku: %s", exc)

    async def scheduler(self) -> None:
        while True:
            at = sync_service.next_run(self.now(), self.settings.sync_times)
            log.info("Następna synchronizacja: %s", at.strftime("%Y-%m-%d %H:%M"))
            await asyncio.sleep(max((at - self.now()).total_seconds(), 1))
            try:
                await self.sync("schedule")
            except ServiceError as exc:
                log.warning("Synchronizacja pominięta: %s", exc)
                await self.refresh()
            except Exception:  # pętla harmonogramu nie może umrzeć
                log.exception("Nieoczekiwany błąd synchronizacji")

    async def session_watch(self) -> None:
        """Status zgody z `GET /sessions` (Enable Banking — bez limitu banku) co kilka godzin."""
        await asyncio.sleep(20)
        while True:
            await self.session_check()
            await asyncio.sleep(SESSION_CHECK_EVERY.total_seconds())

    async def session_check(self) -> None:
        """Jeden przebieg `session_watch` — nigdy nie rzuca, inaczej pętla umiera po cichu."""
        try:
            if not self.missing_config() and sessions.current(self.conn) is not None:
                try:
                    async with self.eb_client() as eb:
                        await sessions.refresh_status(self.conn, eb)
                except (EBError, ServiceError, OSError, httpx.HTTPError) as exc:
                    log.warning("Sprawdzenie zgody nieudane: %s", exc)
                except Exception:
                    log.exception("Nieoczekiwany błąd sprawdzania zgody")
            await self.refresh()
        except Exception:  # pętla zgody nie może umrzeć
            log.exception("Błąd odświeżania encji po sprawdzeniu zgody")

    # --- HA ---------------------------------------------------------------------------------

    def manual_sync_needed(self) -> bool:
        return sync_service.manual_sync_needed(self.conn)

    def inbox(self) -> list[inbox.Item]:
        """Karty dzwonka (panel i encja `sensor.budget_inbox`)."""
        return inbox.items(self.snapshot, self.now(), self.balance_memo)

    def refresh_soon(self) -> None:
        """Odświeżenie encji w tle po zapisie w panelu (kwota, grupa, kategorie)."""
        if self._refresh_task and not self._refresh_task.done():
            return
        self._refresh_task = asyncio.create_task(self._refresh_later())

    async def _refresh_later(self) -> None:
        await asyncio.sleep(REFRESH_DEBOUNCE)
        try:
            await self.refresh()
        except Exception:  # odświeżenie w tle nie może zatrzymać add-onu
            log.exception("Błąd odświeżania encji")

    async def daily_tick(self) -> None:
        """Encje Flex zależą od dnia: odświeżenie tuż po północy."""
        while True:
            now = self.now()  # timestamp(): różnica w czasie rzeczywistym także przy zmianie czasu
            await asyncio.sleep(max(next_midnight(now).timestamp() - now.timestamp(), 1))
            try:
                await self.refresh()
            except Exception:
                log.exception("Błąd odświeżania encji o północy")

    async def refresh(self) -> None:
        """Encje MQTT + powiadomienia z bieżącego stanu bazy."""
        now = self.now()
        if self.publisher is not None:
            await self.publisher.update(
                ha_publisher.build_entities(
                    self.snapshot, now=now, today=now.date(), inbox_items=self.inbox()
                )
            )
        if not self.ha.available:
            return
        alerts = notifications.evaluate(
            sessions.current(self.conn),
            failures=sync_service.consecutive_failures(self.conn),
            manual_sync_needed=self.manual_sync_needed(),
            warning_days=self.settings.consent_warning_days,
            now=now,
            failures_to_alert=sync_service.FAILURES_TO_ALERT,
        )
        try:
            await self.notifier.process(self.conn, alerts, now)
        except Exception:  # powiadomienia nie mogą zatrzymać synchronizacji
            log.exception("Błąd przetwarzania powiadomień")
