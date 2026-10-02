"""Połączenie z bazą i migracje.

Migracje to pliki `migrations/NNN_nazwa.sql`; numer pliku = wersja schematu po jego
wykonaniu (`PRAGMA user_version`). Każda migracja w osobnej transakcji.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

_MIGRATION_RE = re.compile(r"^(\d{3})_[\w-]+\.sql$")


class MigrationError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def migrations() -> list[tuple[int, str, str]]:
    """(wersja, nazwa pliku, SQL) posortowane rosnąco."""
    out = []
    for entry in resources.files("budget.storage").joinpath("migrations").iterdir():
        if m := _MIGRATION_RE.match(entry.name):
            out.append((int(m.group(1)), entry.name, entry.read_text(encoding="utf-8")))
    out.sort()
    versions = [v for v, _, _ in out]
    if versions != list(range(1, len(versions) + 1)):
        raise MigrationError(f"luka albo duplikat w numeracji migracji: {versions}")
    return out


def schema_version(conn: sqlite3.Connection) -> int:
    version: int = conn.execute("PRAGMA user_version").fetchone()[0]
    return version


def migrate(conn: sqlite3.Connection) -> int:
    """Wykonaj brakujące migracje; zwraca wersję schematu."""
    current = schema_version(conn)
    available = migrations()
    if current > len(available):
        raise MigrationError(
            f"baza w wersji {current}, a add-on zna tylko {len(available)} — nowsza baza?"
        )
    for version, name, sql in available[current:]:
        try:
            conn.execute("BEGIN")
            # executescript zatwierdza otwartą transakcję, więc instrukcje idą pojedynczo
            for statement in _statements(sql):
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            conn.execute("ROLLBACK")
            raise MigrationError(f"migracja {name} nie powiodła się: {exc}") from exc
    return schema_version(conn)


def _statements(sql: str) -> list[str]:
    out, buf = [], ""
    for line in sql.splitlines(keepends=True):
        if line.lstrip().startswith("--"):
            continue
        buf += line
        if sqlite3.complete_statement(buf):
            out.append(buf.strip())
            buf = ""
    if buf.strip():
        raise MigrationError("niedokończona instrukcja SQL na końcu migracji")
    return out


def connect(path: Path | str) -> sqlite3.Connection:
    """Połączenie z włączonymi kluczami obcymi i WAL; schemat zmigrowany."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(path, isolation_level=None)  # transakcje jawnie (BEGIN/COMMIT)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn
