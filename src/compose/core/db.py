"""Database access, independent of the engine behind it.

Everything else in compose talks to :class:`Database`: ``execute`` (with ``?`` placeholders),
``transaction`` and ``migrate``. A backend subclasses it, translates placeholders and errors,
and ships its own SQL migrations under ``compose/core/migrations/<dialect>/``. SQLite is the
only backend today (:class:`SqliteDatabase`); register another in :data:`BACKENDS` and pick it
with ``COMPOSE_DATABASE_URL`` (``<scheme>://...``).

Portable SQL only: timestamps are text in one fixed UTC format (see :func:`format_ts`) so they
compare as plain strings, and dates are never computed in SQL.
"""

from __future__ import annotations

import os
import random
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from compose.core.home import Home

BUSY_TIMEOUT_MS = 10_000
DATABASE_URL_ENV = "COMPOSE_DATABASE_URL"


def utcnow() -> datetime:
    return datetime.now(UTC)


def format_ts(moment: datetime) -> str:
    """The one stored form of a timestamp: fixed-width UTC, so text order is time order."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class IntegrityError(Exception):
    """A constraint (check, unique, foreign key) was violated."""


class Row:
    """One result row, readable by position (``row[0]``) or column name (``row["id"]``)."""

    __slots__ = ("_cols", "_vals")

    def __init__(self, cols: Sequence[str], vals: Sequence[Any]) -> None:
        self._cols = tuple(cols)
        self._vals = tuple(vals)

    def __getitem__(self, key: int | str) -> Any:
        return self._vals[self._cols.index(key) if isinstance(key, str) else key]

    def keys(self) -> list[str]:
        return list(self._cols)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._vals)

    def __len__(self) -> int:
        return len(self._vals)


class Result:
    """What :meth:`Database.execute` returns: all rows, already fetched."""

    def __init__(self, rows: list[Row], rowcount: int) -> None:
        self.rows = rows
        self.rowcount = rowcount

    def fetchone(self) -> Any:  # a Row, or None when empty
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[Any]:  # Rows
        return list(self.rows)

    def __iter__(self) -> Iterator[Row]:
        return iter(self.rows)


def _statements(script: str) -> list[str]:
    """Split a migration into statements: one per ``;``. Comments (``--``) are dropped, so
    migrations keep ``;`` and ``--`` out of string literals."""
    lines = [ln.split("--", 1)[0] for ln in script.splitlines()]
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


class Database(ABC):
    """A database. Subclasses: one connection per thread, autocommit outside transactions."""

    dialect: str

    @abstractmethod
    def execute(self, sql: str, params: Sequence[Any] = ()) -> Result:
        """Run one statement (``?`` placeholders). Inside :meth:`transaction` it joins it."""

    @abstractmethod
    def transaction(self) -> Any:
        """Context manager for a write transaction; nested calls use savepoints. Yields
        the database itself."""

    @abstractmethod
    def close(self) -> None: ...

    def _migrations(self) -> list[tuple[int, str, str]]:
        """This dialect's packaged migrations as (version, name, sql), in order."""
        package = resources.files(f"compose.core.migrations.{self.dialect}")
        found: list[tuple[int, str, str]] = []
        for entry in package.iterdir():
            if entry.name.endswith(".sql"):
                found.append((int(entry.name.split("_", 1)[0]), entry.name, entry.read_text()))
        found.sort()
        versions = [v for v, _, _ in found]
        if versions != list(range(1, len(versions) + 1)):
            raise RuntimeError(f"Migration versions must be contiguous from 1, got {versions}")
        return found

    def schema_version(self) -> int:
        self.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        row = self.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0] or 0) if row is not None else 0

    def migrate(self) -> int:
        """Apply pending migrations; safe to call concurrently. Returns the new version."""
        self.schema_version()  # ensures the bookkeeping table exists
        with self.transaction():
            current = self.schema_version()
            for version, name, sql in self._migrations():
                if version <= current:
                    continue
                for stmt in _statements(sql):
                    self.execute(stmt)
                self.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, format_ts(utcnow())),
                )
                current = version
        return current


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


class SqliteDatabase(Database):
    """SQLite in WAL mode; one connection per thread."""

    dialect = "sqlite"

    def __init__(self, path: Path) -> None:
        self.path = path
        self._local = threading.local()

    @property
    def _conn(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, isolation_level=None, timeout=BUSY_TIMEOUT_MS / 1000)
            conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            _with_retry(lambda: conn.execute("PRAGMA journal_mode=WAL"))
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Result:
        try:
            cur = self._conn.execute(sql, tuple(params))
        except sqlite3.IntegrityError as exc:
            raise IntegrityError(str(exc)) from exc
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [Row(cols, vals) for vals in cur.fetchall()] if cols else []
        return Result(rows, cur.rowcount)

    @contextmanager
    def transaction(self) -> Iterator[Database]:
        depth: int = getattr(self._local, "depth", 0)
        if depth == 0:
            self.execute("BEGIN IMMEDIATE")
        else:
            self.execute(f"SAVEPOINT sp{depth}")
        self._local.depth = depth + 1
        try:
            yield self
        except BaseException:
            if depth == 0:
                self.execute("ROLLBACK")
            else:
                self.execute(f"ROLLBACK TO sp{depth}")
                self.execute(f"RELEASE sp{depth}")
            raise
        else:
            if depth == 0:
                self.execute("COMMIT")
            else:
                self.execute(f"RELEASE sp{depth}")
        finally:
            self._local.depth = depth

    def close(self) -> None:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


BACKENDS: dict[str, Callable[[str, Home], Database]] = {
    "sqlite": lambda url, home: SqliteDatabase(
        Path(url.split("://", 1)[1]) if url.split("://", 1)[1] else home.db_path
    ),
}


def open_database(home: Home) -> Database:
    """Open (and migrate) the database: ``$COMPOSE_DATABASE_URL``, else SQLite in the home."""
    url = os.environ.get(DATABASE_URL_ENV) or "sqlite://"
    scheme = url.split("://", 1)[0]
    if scheme not in BACKENDS:
        raise RuntimeError(f"Unknown database backend {scheme!r}; known: {', '.join(BACKENDS)}")
    db = BACKENDS[scheme](url, home)
    db.migrate()
    return db
