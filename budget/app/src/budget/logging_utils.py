"""Logowanie bez danych wrażliwych (SPEC §8): IBAN-y maskowane, JWT/Bearer/`code` wycinane."""

from __future__ import annotations

import logging
import re

_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b")
_JWT_RE = re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+")
_BEARER_RE = re.compile(r"(Bearer\s+)\S+", re.IGNORECASE)
_CODE_RE = re.compile(r"((?:[?&]|\b)code=)[^&\s\"']+")


def mask_iban(iban: str | None) -> str:
    """`PL61109010140000071219812874` → `PL** **** … 2874`."""
    if not iban:
        return ""
    compact = iban.replace(" ", "")
    if len(compact) < 8:
        return "****"
    return f"{compact[:2]}** **** … {compact[-4:]}"


def redact(text: str) -> str:
    text = _BEARER_RE.sub(r"\1***", text)
    text = _JWT_RE.sub("***jwt***", text)
    text = _CODE_RE.sub(r"\1***", text)
    return _IBAN_RE.sub(lambda m: mask_iban(m.group(0)), text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


def setup_logging(level: str = "info") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # httpx loguje pełne URL-e na INFO — przy debugowaniu też przechodzą przez filtr
    logging.getLogger("httpx").setLevel(logging.WARNING)
