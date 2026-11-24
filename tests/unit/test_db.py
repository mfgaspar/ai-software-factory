from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from compose.core.db import Database, SqliteDatabase, _statements, format_ts, open_database
from compose.core.home import Home

EXPECTED_TABLES = {
    "repos",
    "features",
    "runs",
    "step_execs",
    "hook_execs",
    "locks",
    "schema_migrations",
}


def _tables(db: Database) -> set[str]:
    rows = db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r[0] for r in rows} - {"sqlite_sequence"}


def test_migrate_creates_schema(db: Database) -> None:
    assert _tables(db) == EXPECTED_TABLES
    assert db.schema_version() == 2


def test_migrate_is_idempotent(db: Database, home: Home) -> None:
    assert db.migrate() == 2
    again = open_database(home)
    assert again.migrate() == 2
    count = again.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert count == 2
    again.close()


def test_pragmas(db: Database) -> None:
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_transaction_rollback(db: Database) -> None:
    with pytest.raises(RuntimeError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO repos (id, name, path, created_at) VALUES ('r1', 'a', '/a', 'now')"
        )
        raise RuntimeError("boom")
    assert db.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 0


def test_nested_transaction_savepoint(db: Database) -> None:
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO repos (id, name, path, created_at) VALUES ('r1', 'a', '/a', 'now')"
        )
        with pytest.raises(RuntimeError), db.transaction() as inner:
            inner.execute(
                "INSERT INTO repos (id, name, path, created_at) VALUES ('r2', 'b', '/b', 'now')"
            )
            raise RuntimeError("inner")
    ids = [r[0] for r in db.execute("SELECT id FROM repos").fetchall()]
    assert ids == ["r1"]


def test_statements_split_on_semicolons_and_skip_comments() -> None:
    script = "-- header; with semicolon\nCREATE TABLE t (a INT); -- trailing\nDROP TABLE t;\n"
    assert _statements(script) == ["CREATE TABLE t (a INT)", "DROP TABLE t"]


def test_timestamps_have_one_fixed_form() -> None:
    assert format_ts(datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)) == "2026-01-02T03:04:05.000000Z"
    later = datetime(2026, 1, 2, 3, 4, 5, 1, tzinfo=UTC)
    assert format_ts(datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)) < format_ts(later)


def test_unknown_backend_is_refused(home: Home, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPOSE_DATABASE_URL", "nosuchdb://x")
    with pytest.raises(RuntimeError, match="Unknown database backend"):
        open_database(home)


_WRITER = """
import sys
from pathlib import Path
from compose.core.db import SqliteDatabase
db = SqliteDatabase(Path(sys.argv[1]))
db.migrate()
tag = sys.argv[2]
for i in range(150):
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO repos (id, name, path, created_at) VALUES (?, ?, ?, 'now')",
            (f"{tag}{i}", f"{tag}{i}", f"/{tag}/{i}"),
        )
"""


def test_concurrent_writers_from_two_processes(home: Home, tmp_path: Path) -> None:
    script = tmp_path / "writer.py"
    script.write_text(_WRITER)
    procs = [
        subprocess.Popen(
            [sys.executable, str(script), str(home.db_path), tag], stderr=subprocess.PIPE
        )
        for tag in ("a", "b")
    ]
    for proc in procs:
        _, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err.decode()
    db = SqliteDatabase(home.db_path)
    assert db.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 300
    db.close()
