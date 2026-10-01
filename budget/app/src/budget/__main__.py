"""Punkt wejścia add-onu (`python -m budget`). Usługa (sync + panel) powstaje w M3/M6."""

from __future__ import annotations

import logging
import sys

from budget import __version__
from budget.logging_utils import setup_logging
from budget.settings import SettingsError, load_settings

log = logging.getLogger("budget")


def main() -> int:
    try:
        settings = load_settings()
    except SettingsError as exc:
        setup_logging()
        log.error("%s", exc)
        return 2
    setup_logging(settings.log_level)
    log.info("Budżet Domowy %s (konfiguracja: %s)", __version__, settings.source)
    log.warning("Usługa synchronizacji i panel nie są jeszcze zaimplementowane (M3/M6).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
