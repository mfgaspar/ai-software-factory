"""SQLite access: connections, transactions and schema migrations."""

from __future__ import annotations

import random
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from compose.core.home import Home

BUSY_TIMEOUT_MS = 10_000


def utcnow() -> datetime:
    return datetime.now(UTC)


def _is_blank(sql: str) -> bool:
    return all(not line.strip() or line.strip().startswith("--") for line in sql.splitlines())


def _split_statements(script: str) -> list[str]:
    """Split a SQL script into complete statements (handles comments and triggers)."""
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if not _is_blank(buffer):
        raise ValueError(f"Incomplete SQL statement in migration: {buffer.strip()[:80]}")
    return statements


def _migrations() -> list[tuple[int, str, str]]:
    """All packaged migrations as (version, name, sql), in order."""
    found: list[tuple[int, str, str]] = []
    for entry in resources.files("compose.core.migrations").iterdir():
        name = entry.name
        if not name.endswith(".sql"):
            continue
        version = int(name.split("_", 1)[0])
        found.append((version, name, entry.read_text()))
    found.sort()
    versions = [v for v, _, _ in found]
    if versions != list(range(1, len(versions) + 1)):
        raise RuntimeError(f"Migration versions must be contiguous from 1, got {versions}")
    return found


def _with_retry(action: Callable[[], object], attempts: int = 100) -> None:
    """Retry an operation SQLite reports as locked without consulting the busy handler.

    Switching a brand-new database to WAL needs an exclusive lock and fails at once with
    "database is locked" when two processes create the database at the same moment.
    """
    for attempt in range(attempts):
        try:
            action()
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) or attempt == attempts - 1:
                raise
            time.sleep(0.02 + random.random() * 0.03)


class Database:
    """One SQLite database file; one connection per thread.

    Connections run in autocommit mode; use :meth:`transaction` to group writes.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._local = threading.local()

    @property
    def conn(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, isolation_level=None, timeout=BUSY_TIMEOUT_MS / 1000)
            conn.row_factory = sqlite3.Row
            conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            _with_retry(lambda: conn.execute("PRAGMA journal_mode=WAL"))
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """A write transaction (``BEGIN IMMEDIATE``); nested calls use savepoints."""
        conn = self.conn
        depth: int = getattr(self._local, "depth", 0)
        if depth == 0:
            conn.execute("BEGIN IMMEDIATE")
        else:
            conn.execute(f"SAVEPOINT sp{depth}")
        self._local.depth = depth + 1
        try:
            yield conn
        except BaseException:
            if depth == 0:
                conn.execute("ROLLBACK")
            else:
                conn.execute(f"ROLLBACK TO sp{depth}")
                conn.execute(f"RELEASE sp{depth}")
            raise
        else:
            if depth == 0:
                conn.execute("COMMIT")
            else:
                conn.execute(f"RELEASE sp{depth}")
        finally:
            self._local.depth = depth

    def schema_version(self) -> int:
        conn = self.conn
        _with_retry(
            lambda: conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )
        )
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0] or 0)

    def migrate(self) -> int:
        """Apply pending migrations; safe to call concurrently. Returns the new version."""
        self.schema_version()  # ensures the bookkeeping table exists
        with self.transaction() as conn:
            current = self.schema_version()
            for version, name, sql in _migrations():
                if version <= current:
                    continue
                for stmt in _split_statements(sql):
                    conn.execute(stmt)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, utcnow().isoformat()),
                )
                current = version
        return current

    def close(self) -> None:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


def open_database(home: Home) -> Database:
    """Open (and migrate) the compose database in the given home."""
    db = Database(home.db_path)
    db.migrate()
    return db
