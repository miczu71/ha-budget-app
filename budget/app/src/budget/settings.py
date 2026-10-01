"""Konfiguracja add-onu.

Produkcja: opcje użytkownika z `/data/options.json` (Supervisor). Dev: brak tego pliku →
zmienne `BUDGET_*` z `.env` (ścieżka w `BUDGET_ENV_FILE`) nadpisywane przez środowisko.
Ścieżki katalogów (`BUDGET_CONFIG_DIR`, `BUDGET_DATA_DIR`) i `BUDGET_EB_BASE_URL` zawsze
można nadpisać ze środowiska — nie są opcjami widocznymi w UI.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_OPTIONS_PATH = "/data/options.json"
DEFAULT_EB_BASE_URL = "https://api.enablebanking.com"
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_ENV_PREFIX = "BUDGET_"


class SettingsError(Exception):
    """Błędna lub niekompletna konfiguracja — komunikat ma być czytelny dla użytkownika."""


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    eb_application_id: str | None = None
    eb_private_key_file: str = "enablebanking.pem"
    eb_redirect_url: str | None = None
    eb_base_url: str = DEFAULT_EB_BASE_URL
    sync_times: tuple[str, ...] = ("06:30", "13:30", "21:30")
    currency: str = "PLN"
    month_start_day: int = Field(default=1, ge=1, le=28)
    consent_warning_days: int = Field(default=14, ge=1, le=60)
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    config_dir: Path = Path("/config")
    data_dir: Path = Path("/data")
    source: Literal["options", "env"] = "options"

    @field_validator("sync_times", mode="before")
    @classmethod
    def _split_times(cls, value: Any) -> Any:
        if isinstance(value, str):
            return tuple(t.strip() for t in value.split(",") if t.strip())
        return value

    @field_validator("sync_times")
    @classmethod
    def _check_times(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        bad = [t for t in value if not _TIME_RE.match(t)]
        if bad:
            raise ValueError(f"nieprawidłowe godziny w sync_times (oczekiwane HH:MM): {bad}")
        return tuple(sorted(set(value)))

    @field_validator("eb_application_id", "eb_redirect_url", mode="before")
    @classmethod
    def _blank_is_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def private_key_path(self) -> Path:
        path = Path(self.eb_private_key_file)
        return path if path.is_absolute() else self.config_dir / path


def _env_overrides(env: Mapping[str, str | None]) -> dict[str, Any]:
    fields = set(Settings.model_fields) - {"source"}
    out: dict[str, Any] = {}
    for key, value in env.items():
        if value is None or not key.startswith(_ENV_PREFIX):
            continue
        name = key.removeprefix(_ENV_PREFIX).lower()
        if name in fields:
            out[name] = value
    return out


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Wczytaj ustawienia; `env` domyślnie `os.environ` (parametr dla testów)."""
    env = os.environ if env is None else env
    options_path = Path(env.get("BUDGET_OPTIONS_PATH", DEFAULT_OPTIONS_PATH))

    data: dict[str, Any]
    if options_path.is_file():
        try:
            data = json.loads(options_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SettingsError(f"{options_path}: niepoprawny JSON ({exc})") from exc
        data["source"] = "options"
        # Z env tylko ścieżki/URL — nie opcje użytkownika
        for name in ("config_dir", "data_dir", "eb_base_url"):
            if (value := env.get(_ENV_PREFIX + name.upper())) is not None:
                data[name] = value
    else:
        env_file = env.get("BUDGET_ENV_FILE", ".env")
        data = _env_overrides(dotenv_values(env_file)) if Path(env_file).is_file() else {}
        data.update(_env_overrides(env))
        data["source"] = "env"

    try:
        return Settings.model_validate(data)
    except ValueError as exc:
        raise SettingsError(f"niepoprawna konfiguracja: {exc}") from exc


def resolve_private_key_path(settings: Settings) -> Path:
    """Ścieżka do PEM klucza EB; czytelny błąd z instrukcją, gdy pliku brak (SPEC §8)."""
    path = settings.private_key_path
    if not path.is_file():
        raise SettingsError(
            f"Brak klucza prywatnego Enable Banking: {path}. Wygeneruj klucz "
            "(`python -m budget.cli keygen`) albo pobierz .pem z Control Panelu Enable Banking "
            f"i zapisz go jako '{settings.eb_private_key_file}' w katalogu konfiguracji add-onu "
            "(/addon_configs/<repo>_budget/). Nie wklejaj klucza do opcji add-onu."
        )
    return path
