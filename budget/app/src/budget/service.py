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
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx

from budget import forecast as forecast_mod
from budget import (
    fx,
    ha_publisher,
    inbox,
    invest,
    invest_blogs,
    invest_sources,
    invest_why,
    ledger,
    lidl_link,
    loan,
    networth,
    notifications,
    promo_watch,
    savings,
    sessions,
    stocks,
    summary,
    sync_service,
    wibor,
    year,
)
from budget.categorize import engine as categorize
from budget.eb_client import EBClient, EBError, PsuHeaders
from budget.ha_client import HAClient, HAError
from budget.recurring import detect
from budget.settings import Settings, SettingsError, resolve_private_key_path
from budget.snapshot import Snapshot
from budget.suggest import engine as suggest
from budget.sync_service import SyncResult

log = logging.getLogger(__name__)
PAYDAY_PUSH_DAYS = 3  # wypłata wykryta przy synchronizacji bywa o dzień spóźniona

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
        self.forecast_memo = forecast_mod.ForecastMemo()
        self.year_memo = year.Memo()
        self.advice_memo = invest.AdviceMemo()
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
        self.link_lidl()
        self.detect_series()
        await self.refresh()
        await self.refresh_calendar()
        self.suggest_later()
        return result

    # --- paragony Lidl (M29) -------------------------------------------------------------------

    def link_lidl(self) -> lidl_link.MatchResult | None:
        """Dopasowanie paragonów z add-onu Lidl po synchronizacji; błąd jej nie zatrzymuje."""
        try:
            receipts = lidl_link.load(self.settings.lidl_receipts_path)
            with ledger.transaction(self.conn):
                result = lidl_link.match(self.conn, receipts)
                if result.linked:  # zwroty dziedziczą kategorię zakupu
                    categorize.recategorize(self.conn)
        except Exception:
            log.exception("Błąd dopasowania paragonów Lidl")
            return None
        if receipts:
            log.info(
                "Paragony Lidl: %d połączonych, %d do wyboru, %d bez płatności, %s zł poza spoż.",
                result.linked, result.ambiguous, result.unmatched, result.moved,
            )  # fmt: skip
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

    # --- podsumowania i kalendarz (M6) -------------------------------------------------------

    async def send_summary(self, msg: summary.Message) -> None:
        """Wysyłka przez `summary_notify_service`; rzuca `ServiceError`, gdy się nie da."""
        target = self.settings.summary_notify_service
        if not target:
            raise ServiceError("Podsumowania wyłączone — ustaw opcję summary_notify_service.")
        url = self.notifier.panel_url
        data = {"clickAction": url, "url": url} if url else None
        try:
            await self.ha.notify(target, msg.title, msg.text, data)
        except HAError as exc:
            raise ServiceError(f"{target}: {exc}") from exc
        log.info("Podsumowanie %s (%s) wysłane do %s", msg.kind, msg.period, target)

    async def send_due_summaries(self) -> None:
        """Jeden przebieg `summaries` — nigdy nie rzuca."""
        if not self.settings.summary_notify_service or not self.ha.available:
            return
        try:
            async with self.lock:  # poranna synchronizacja najpierw
                due = summary.due(self.snapshot, self.now(), self.invest_due)
            for msg in due:
                await self.send_summary(msg)
                summary.mark_sent(self.conn, msg)
        except ServiceError as exc:
            log.warning("Podsumowanie niewysłane: %s", exc)
        except Exception:
            log.exception("Błąd podsumowania")

    async def watch_promo(self) -> None:
        """Odczyt regulaminu promocji Profit (M10 E7) — tylko gdy jest konto oszczędnościowe."""
        if savings.all_accounts(self.conn):
            await promo_watch.refresh(self.conn, self.now())

    async def watch_wibor(self) -> None:
        """Odczyt notowań WIBOR 3M (M9 E4) — tylko gdy jest kredyt."""
        loans = loan.all_loans(self.conn)
        if loans:
            today = self.now().date()
            wanted = [
                wibor.fixing_day(d)
                for lo in loans
                if lo.rate_reset_date
                for d in loan.resets(lo.rate_reset_date, today)
            ]
            await wibor.refresh(self.conn, self.now(), wanted)

    async def watch_invest(self) -> None:
        """Oferty obligacji, rankingu i blogów (M22 E2/E3) — raz na dobę, mimo restartów."""
        now = self.now()
        try:
            if invest_sources.due(self.conn, now):
                await invest_sources.refresh(self.conn, now)
                await invest_blogs.refresh(self.conn, self.settings, now)
        except Exception:  # pętla podsumowań nie może umrzeć
            log.exception("Błąd odczytu ofert inwestycyjnych")

    def invest_advice(self) -> invest.Advice | None:
        """Rekomendacja agenta inwestycyjnego (M22 E4); błąd nie blokuje podsumowań."""
        try:
            return self.advice_memo.get(
                self.snapshot, self.forecast(), self.year_projection(), self.now().date()
            )
        except Exception:
            log.exception("Rekomendacja agenta inwestycyjnego nieudana")
            return None

    def invest_due(self) -> summary.Message | None:
        """Push agenta inwestycyjnego po wypłacie (do `PAYDAY_PUSH_DAYS` dni po jej wykryciu, raz
        na wypłatę); poza oknem bez liczenia rekomendacji."""
        fc = self.forecast()
        today = self.now().date()
        if (
            fc is None
            or fc.period_start is None
            or not 0 <= (today - fc.period_start).days <= PAYDAY_PUSH_DAYS
        ):
            return None
        adv = self.invest_advice()
        return (
            summary.invest_message(adv, invest_why.text(self.conn, adv, self.snapshot))
            if adv
            else None
        )

    async def watch_invest_why(self) -> None:
        """Uzasadnienie rekomendacji od modelu — tylko po zmianie rekomendacji (M22 E4)."""
        adv = self.invest_advice()
        try:
            if adv:
                await invest_why.refresh(self.conn, self.settings, adv, self.now())
        except Exception:  # pętla podsumowań nie może umrzeć
            log.exception("Błąd uzasadnienia rekomendacji")

    async def summaries(self) -> None:
        """Podsumowania o `summary.SEND_AT`; zaległe z dzisiaj zaraz po starcie."""
        while True:
            await self.watch_promo()
            await self.watch_wibor()
            await self.watch_invest()
            await self.watch_invest_why()
            await self.send_due_summaries()
            now = self.now()
            await asyncio.sleep(max(summary.next_send(now).timestamp() - now.timestamp(), 1))

    async def refresh_calendar(self) -> None:
        """Remote Calendar w HA pobiera ICS raz na dobę — po synchronizacji wcześniej."""
        if not self.settings.calendar_entity or not self.ha.available:
            return
        try:
            await self.ha.update_entity(self.settings.calendar_entity)
        except HAError as exc:
            log.warning("Odświeżenie %s nieudane: %s", self.settings.calendar_entity, exc)

    # --- HA ---------------------------------------------------------------------------------

    def manual_sync_needed(self) -> bool:
        return sync_service.manual_sync_needed(self.conn)

    def inbox_all(self) -> list[inbox.Item]:
        """Wszystkie karty dzwonka, także ręcznie ukryte."""
        return inbox.items(self.snapshot, self.now(), self.balance_memo, self.forecast())

    def inbox(self) -> list[inbox.Item]:
        """Karty dzwonka (panel i encja `sensor.budget_inbox`); bez ręcznie ukrytych."""
        return inbox.visible(self.conn, self.inbox_all())

    def forecast(self) -> forecast_mod.Forecast | None:
        """Prognoza do wypłaty dla dzwonka i encji; błąd prognozy nie blokuje reszty."""
        now = self.now()
        try:
            return self.forecast_memo.get(
                self.snapshot, now.date(), now, Decimal(self.settings.forecast_buffer)
            )
        except Exception:
            log.exception("Prognoza do wypłaty nieudana")
            return None

    def year_projection(self) -> year.Projection | None:
        """Prognoza roczna dla encji; błąd prognozy nie blokuje reszty."""
        now = self.now()
        try:
            return self.year_memo.get(
                self.snapshot, now.date(), Decimal(self.settings.forecast_buffer)
            )
        except Exception:
            log.exception("Prognoza roczna nieudana")
            return None

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

    async def record_networth(self) -> None:
        """Migawka majątku netto (M26): kursy NBP, jednorazowe odtworzenie historii (gdy brak
        migawek), potem wpis na dziś; błąd nie zatrzymuje reszty."""
        today = self.now().date()
        try:
            await stocks.refresh(self.conn, self.ha, self.settings.stocks_entity_prefix, self.now())
        except Exception:
            log.exception("Odczyt akcji nieudany")
        try:
            await fx.refresh(self.conn, today)
            first = networth.first_day(self.conn)
            if first is not None and not networth.has_history(self.conn, today):
                await fx.refresh(self.conn, today, since=first)
                if fx.covers(self.conn, first):  # bez kursów EUR wyszłoby 0 zł; ponowimy jutro
                    networth.backfill(self.conn, today)
                else:
                    log.warning("Historia majątku czeka na kursy NBP")
            try:
                await stocks.backfill_history(
                    self.conn, self.ha, self.settings.stocks_entity_prefix, today
                )
            except Exception:
                log.exception("Historia akcji nieudana")
            adv = self.invest_advice()
            spend = adv.inputs.spend if adv and adv.inputs.spend > 0 else None
            networth.save(self.conn, networth.compute(self.conn, today, spend, snap=self.snapshot))
        except Exception:
            log.exception("Migawka majątku netto nieudana")

    async def daily_tick(self) -> None:
        """Encje Flex zależą od dnia: odświeżenie tuż po północy (i migawka majątku netto)."""
        await self.record_networth()
        while True:
            now = self.now()  # timestamp(): różnica w czasie rzeczywistym także przy zmianie czasu
            await asyncio.sleep(max(next_midnight(now).timestamp() - now.timestamp(), 1))
            await self.record_networth()
            try:
                await self.refresh()
            except Exception:
                log.exception("Błąd odświeżania encji o północy")

    async def refresh(self) -> None:
        """Encje MQTT + powiadomienia z bieżącego stanu bazy."""
        now = self.now()
        try:
            await stocks.refresh(self.conn, self.ha, self.settings.stocks_entity_prefix, now)
        except Exception:
            log.exception("Odczyt akcji nieudany")
        if self.publisher is not None:
            await self.publisher.update(
                ha_publisher.build_entities(
                    self.snapshot,
                    now=now,
                    today=now.date(),
                    inbox_items=self.inbox(),
                    forecast=self.forecast(),
                    year_proj=self.year_projection(),
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
