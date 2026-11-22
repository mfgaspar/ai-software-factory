from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from compose.core.db import Database, _split_statements, open_database
from compose.core.home import Home

EXPECTED_TABLES = {
    "repos",
    "features",
    "runs",
    "step_execs",
    "hook_execs",
    "actions",
    "file_changes",
    "locks",
    "schema_migrations",
}


def _tables(db: Database) -> set[str]:
    rows = db.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r[0] for r in rows} - {"sqlite_sequence"}


def test_migrate_creates_schema(db: Database) -> None:
    assert _tables(db) == EXPECTED_TABLES
    assert db.schema_version() == 1


def test_migrate_is_idempotent(db: Database, home: Home) -> None:
    assert db.migrate() == 1
    again = open_database(home)
    assert again.migrate() == 1
    count = again.conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert count == 1
    again.close()


def test_pragmas(db: Database) -> None:
    assert db.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_transaction_rollback(db: Database) -> None:
    with pytest.raises(RuntimeError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO repos (id, name, path, created_at) VALUES ('r1', 'a', '/a', 'now')"
        )
        raise RuntimeError("boom")
    assert db.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 0


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
    ids = [r[0] for r in db.conn.execute("SELECT id FROM repos").fetchall()]
    assert ids == ["r1"]


def test_split_statements_handles_comments_and_triggers() -> None:
    script = (
        "-- header; with semicolon in comment\n"
        "CREATE TABLE t (a INT); -- trailing\n"
        "CREATE TRIGGER tr AFTER INSERT ON t BEGIN\n"
        "  UPDATE t SET a = 1;\n"
        "END;\n"
        "-- footer\n"
    )
    statements = _split_statements(script)
    assert len(statements) == 2
    assert "CREATE TABLE t" in statements[0]
    assert "CREATE TRIGGER tr" in statements[1] and statements[1].endswith("END;")


def test_split_statements_rejects_incomplete() -> None:
    with pytest.raises(ValueError):
        _split_statements("CREATE TABLE t (a INT)")


_WRITER = """
import sys
from pathlib import Path
from compose.core.db import Database
db = Database(Path(sys.argv[1]))
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
    db = Database(home.db_path)
    assert db.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 300
    db.close()
