import json
from pathlib import Path

import pytest

from budget.settings import SettingsError, load_settings, resolve_private_key_path


def _options(tmp_path: Path, **overrides: object) -> Path:
    data: dict[str, object] = {
        "eb_application_id": "app-123",
        "eb_private_key_file": "enablebanking.pem",
        "eb_redirect_url": "https://ha.example/budget-callback",
        "sync_times": ["21:30", "06:30", "13:30"],
        "currency": "PLN",
        "month_start_day": 10,
        "consent_warning_days": 14,
        "log_level": "debug",
    }
    data.update(overrides)
    path = tmp_path / "options.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_reads_options_json(tmp_path: Path) -> None:
    path = _options(tmp_path)
    s = load_settings({"BUDGET_OPTIONS_PATH": str(path), "BUDGET_CONFIG_DIR": str(tmp_path)})
    assert s.source == "options"
    assert s.eb_application_id == "app-123"
    assert s.sync_times == ("06:30", "13:30", "21:30")  # posortowane
    assert s.month_start_day == 10
    assert s.private_key_path == tmp_path / "enablebanking.pem"


def test_options_json_ignores_user_options_from_env(tmp_path: Path) -> None:
    path = _options(tmp_path)
    s = load_settings({"BUDGET_OPTIONS_PATH": str(path), "BUDGET_CURRENCY": "EUR"})
    assert s.currency == "PLN"


def test_options_null_application_id_is_allowed(tmp_path: Path) -> None:
    path = _options(tmp_path, eb_application_id=None, eb_redirect_url=None)
    s = load_settings({"BUDGET_OPTIONS_PATH": str(path)})
    assert s.eb_application_id is None


def test_env_fallback_with_dotenv_and_env_override(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BUDGET_EB_APPLICATION_ID=from-dotenv\n"
        "BUDGET_SYNC_TIMES=07:00, 19:00\n"
        "BUDGET_CURRENCY=EUR\n"
        "OTHER=ignored\n",
        encoding="utf-8",
    )
    s = load_settings(
        {
            "BUDGET_OPTIONS_PATH": str(tmp_path / "missing.json"),
            "BUDGET_ENV_FILE": str(env_file),
            "BUDGET_CURRENCY": "PLN",
            "BUDGET_EB_BASE_URL": "https://sandbox.example",
        }
    )
    assert s.source == "env"
    assert s.eb_application_id == "from-dotenv"
    assert s.sync_times == ("07:00", "19:00")
    assert s.currency == "PLN"  # env wygrywa z .env
    assert s.eb_base_url == "https://sandbox.example"


@pytest.mark.parametrize("times", [["24:00"], ["6:30"], ["06:60"], ["abc"]])
def test_invalid_sync_times(tmp_path: Path, times: list[str]) -> None:
    path = _options(tmp_path, sync_times=times)
    with pytest.raises(SettingsError, match="sync_times"):
        load_settings({"BUDGET_OPTIONS_PATH": str(path)})


@pytest.mark.parametrize("day", [0, 29])
def test_month_start_day_range(tmp_path: Path, day: int) -> None:
    path = _options(tmp_path, month_start_day=day)
    with pytest.raises(SettingsError, match="month_start_day"):
        load_settings({"BUDGET_OPTIONS_PATH": str(path)})


def test_broken_json(tmp_path: Path) -> None:
    path = tmp_path / "options.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(SettingsError, match="niepoprawny JSON"):
        load_settings({"BUDGET_OPTIONS_PATH": str(path)})


def test_missing_private_key_has_instructions(tmp_path: Path) -> None:
    path = _options(tmp_path)
    s = load_settings({"BUDGET_OPTIONS_PATH": str(path), "BUDGET_CONFIG_DIR": str(tmp_path)})
    with pytest.raises(SettingsError, match="keygen") as exc:
        resolve_private_key_path(s)
    assert "addon_configs" in str(exc.value)


def test_private_key_found_and_absolute_path(tmp_path: Path) -> None:
    pem = tmp_path / "keys" / "k.pem"
    pem.parent.mkdir()
    pem.write_text("x", encoding="utf-8")
    path = _options(tmp_path, eb_private_key_file=str(pem))
    s = load_settings({"BUDGET_OPTIONS_PATH": str(path)})
    assert resolve_private_key_path(s) == pem
