"""Spójność pakietu add-onu: config.yaml ↔ ustawienia, wersje, Dockerfile."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import yaml

from budget import __version__
from budget.settings import load_settings

ADDON = Path(__file__).resolve().parents[2]
CONFIG = yaml.safe_load((ADDON / "config.yaml").read_text(encoding="utf-8"))


def test_default_options_load(tmp_path: Path) -> None:
    """Domyślne opcje, które Supervisor zapisze do /data/options.json, muszą się wczytać."""
    path = tmp_path / "options.json"
    path.write_text(json.dumps(CONFIG["options"]), encoding="utf-8")
    s = load_settings({"BUDGET_OPTIONS_PATH": str(path)})
    assert s.eb_application_id is None and s.eb_redirect_url is None
    assert s.notify_service is None
    assert s.sync_times == ("06:30", "13:30", "21:30")


def test_every_option_has_schema_and_translation() -> None:
    assert set(CONFIG["options"]) == set(CONFIG["schema"])
    for lang in ("pl", "en"):
        tr = yaml.safe_load((ADDON / "translations" / f"{lang}.yaml").read_text(encoding="utf-8"))
        assert set(tr["configuration"]) == set(CONFIG["options"]), lang


def test_versions_match() -> None:
    assert CONFIG["version"] == __version__
    pyproject = (ADDON / "app" / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(rf'^version = "{re.escape(__version__)}"$', pyproject, re.M)


def test_dockerfile_pins_base_image_and_port() -> None:
    dockerfile = (ADDON / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^FROM python:3\.12-alpine3\.\d+$", dockerfile, re.M)
    assert CONFIG["ingress_port"] == 8099
    requirements = (ADDON / "requirements.txt").read_text(encoding="utf-8")
    pinned = [line for line in requirements.splitlines() if line and not line.startswith("#")]
    assert pinned and all("==" in line for line in pinned)


def test_package_data_covers_every_static_file() -> None:
    """Obraz robi `pip install .` i kasuje `src`: plik spoza globów zniknąłby w produkcji."""
    pyproject = tomllib.loads((ADDON / "app" / "pyproject.toml").read_text(encoding="utf-8"))
    globs = pyproject["tool"]["setuptools"]["package-data"]["budget.web"]
    web = ADDON / "app" / "src" / "budget" / "web"
    missing = [
        str(f.relative_to(web))
        for f in (web / "static").rglob("*")
        if f.is_file() and not any(f.relative_to(web).match(g) for g in globs)
    ]
    assert not missing, missing
