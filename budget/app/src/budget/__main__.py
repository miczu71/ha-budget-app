"""Punkt wejścia add-onu (`python -m budget`): panel + harmonogram + MQTT w jednej pętli.

CLI deweloperskie pozostaje pod `python -m budget.cli`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import uvicorn

from budget import __version__, ha_publisher, ledger
from budget.categorize import engine as categorize
from budget.ha_client import HAClient
from budget.logging_utils import setup_logging
from budget.service import Service
from budget.settings import Settings, SettingsError, load_settings
from budget.storage import db
from budget.web.app import create_app

log = logging.getLogger("budget")

PORT = 8099


def _timezone() -> ZoneInfo:
    try:
        return ZoneInfo(os.environ.get("TZ") or "Europe/Warsaw")
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("Nieznana strefa TZ=%r — używam Europe/Warsaw", os.environ.get("TZ"))
        return ZoneInfo("Europe/Warsaw")


async def serve(settings: Settings) -> None:
    conn = db.connect(settings.db_path)
    # Słownik i silnik mogły się zmienić z wersją add-onu — kategorie liczone od nowa
    with ledger.transaction(conn):
        changed = categorize.recategorize(conn)
    log.info("Kategorie przeliczone (zmienionych transakcji: %d)", changed)
    ha = HAClient(os.environ.get("SUPERVISOR_TOKEN"))
    service = Service(settings, conn, ha, tz=_timezone())
    if (slug := await ha.self_slug()) is not None:
        service.notifier.panel_url = f"/hassio/ingress/{slug}"

    tasks: list[asyncio.Task[None]] = []
    mqtt = await ha.mqtt_service()
    if mqtt:
        service.publisher = ha_publisher.Publisher(
            host=str(mqtt["host"]),
            port=int(mqtt.get("port") or 1883),
            username=mqtt.get("username"),
            password=mqtt.get("password"),
            on_sync_now=service.sync_from_button,
        )
        tasks.append(asyncio.create_task(service.publisher.run()))
    else:
        log.warning("Brak brokera MQTT — encje w HA nie będą publikowane")

    server = uvicorn.Server(
        uvicorn.Config(
            create_app(service, dev=settings.dev),
            host="0.0.0.0",  # dostęp ogranicza allowlista Ingress w aplikacji
            port=int(os.environ.get("BUDGET_PORT") or PORT),
            proxy_headers=False,  # adres klienta = proxy Ingress (allowlista)
            log_level="warning",
            access_log=False,
        )
    )
    tasks += [
        asyncio.create_task(service.scheduler()),
        asyncio.create_task(service.session_watch()),
        asyncio.create_task(service.daily_tick()),
    ]
    log.info("Budżet Domowy %s — panel na porcie %d", __version__, server.config.port)
    try:
        await server.serve()
    finally:
        if service.publisher is not None:
            await service.publisher.offline()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await ha.aclose()
        conn.close()
        log.info("Zatrzymano")


def main() -> int:
    try:
        settings = load_settings()
    except SettingsError as exc:
        setup_logging()
        log.error("%s", exc)
        return 2
    setup_logging(settings.log_level)
    log.info("Konfiguracja: %s, dane: %s", settings.source, settings.data_dir)
    # uvicorn po zamknięciu ponawia przechwycony SIGTERM; jako KeyboardInterrupt przechodzi
    # przez `finally` w serve() (offline w MQTT, zamknięcie bazy) zamiast zabić proces
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve(settings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
