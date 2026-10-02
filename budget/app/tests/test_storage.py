import sqlite3
from pathlib import Path

import pytest

from budget.storage import db


def test_migrations_are_numbered_without_gaps() -> None:
    versions = [v for v, _, _ in db.migrations()]
    assert versions == list(range(1, len(versions) + 1))


def test_connect_migrates_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "ledger.db"
    conn = db.connect(path)
    latest = len(db.migrations())
    assert db.schema_version(conn) == latest
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"account", "account_alias", "txn", "txn_ref", "csv_row", "import_batch"} <= tables
    conn.close()
    conn = db.connect(path)  # drugi raz: nic do zrobienia
    assert db.migrate(conn) == latest


def test_foreign_keys_enforced() -> None:
    conn = db.connect(":memory:")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO account_alias (source, value, account_id) VALUES ('eb_uid', 'x', 999)"
        )


def test_newer_database_is_refused() -> None:
    conn = db.connect(":memory:")
    conn.execute("PRAGMA user_version = 999")
    with pytest.raises(db.MigrationError):
        db.migrate(conn)


def test_failed_migration_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    bad = [(1, "001_bad.sql", "CREATE TABLE a (x INTEGER);\nCREATE TABLE a (x INTEGER);\n")]
    monkeypatch.setattr(db, "migrations", lambda: bad)
    with pytest.raises(db.MigrationError):
        db.migrate(conn)
    assert db.schema_version(conn) == 0
    assert conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0
