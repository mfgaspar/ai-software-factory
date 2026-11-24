"""Cross-process locks stored in the database (e.g. one active run per feature).

A lock row records its owner's pid, hostname and a heartbeat. A lock is *stale*, and may
be taken over, when its owner process on this host is gone or its heartbeat is older than
``stale_after`` seconds.
"""

from __future__ import annotations

import os
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from types import TracebackType

from compose.core import procs
from compose.core.db import Database

DEFAULT_STALE_AFTER = 60.0
DEFAULT_HEARTBEAT_INTERVAL = 15.0


def feature_lock_key(feature_id: str) -> str:
    return f"feature:{feature_id}"


def repo_lock_key(repo_id: str) -> str:
    """The lock of a repo's (single) active repo-scoped run, e.g. clarity."""
    return f"clarity:{repo_id}"


@dataclass(frozen=True)
class LockInfo:
    key: str
    owner: str
    pid: int
    hostname: str
    run_id: str | None
    acquired_at: float
    heartbeat_at: float


class LockHeld(Exception):
    """Someone else holds a live lock."""

    def __init__(self, info: LockInfo) -> None:
        holder = f"run {info.run_id}" if info.run_id else f"pid {info.pid}"
        super().__init__(f"{info.key} is locked by {holder} on {info.hostname}")
        self.info = info


class LockLost(Exception):
    """Our lock was taken over (it went stale) or removed."""


def _pid_alive(pid: int) -> bool:
    return procs.pid_alive(pid)


def is_stale(info: LockInfo, *, stale_after: float = DEFAULT_STALE_AFTER) -> bool:
    if info.hostname == socket.gethostname() and not _pid_alive(info.pid):
        return True
    return time.time() - info.heartbeat_at > stale_after


def read_lock(db: Database, key: str) -> LockInfo | None:
    row = db.execute("SELECT * FROM locks WHERE key = ?", (key,)).fetchone()
    return None if row is None else LockInfo(**dict(row))


class Lock:
    """A held lock. Use as a context manager, or call :meth:`release`."""

    def __init__(self, db: Database, info: LockInfo) -> None:
        self.db = db
        self.info = info
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def key(self) -> str:
        return self.info.key

    def heartbeat(self) -> None:
        cur = self.db.execute(
            "UPDATE locks SET heartbeat_at = ? WHERE key = ? AND owner = ?",
            (time.time(), self.key, self.info.owner),
        )
        if cur.rowcount != 1:
            raise LockLost(f"lost lock {self.key}")

    def keep_alive(self, interval: float = DEFAULT_HEARTBEAT_INTERVAL) -> None:
        """Heartbeat from a daemon thread until released."""
        if self._thread is not None:
            return

        def beat() -> None:
            # The thread gets its own connection (Database is per-thread).
            while not self._stop.wait(interval):
                try:
                    self.heartbeat()
                except LockLost:
                    return

        self._thread = threading.Thread(target=beat, name=f"lock:{self.key}", daemon=True)
        self._thread.start()

    def release(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM locks WHERE key = ? AND owner = ?", (self.key, self.info.owner)
            )

    def __enter__(self) -> Lock:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


def acquire(
    db: Database,
    key: str,
    *,
    run_id: str | None = None,
    stale_after: float = DEFAULT_STALE_AFTER,
) -> Lock:
    """Take the lock or raise :class:`LockHeld`. Stale locks are taken over."""
    now = time.time()
    info = LockInfo(
        key=key,
        owner=uuid.uuid4().hex,
        pid=os.getpid(),
        hostname=socket.gethostname(),
        run_id=run_id,
        acquired_at=now,
        heartbeat_at=now,
    )
    with db.transaction() as conn:
        current = read_lock(db, key)
        if current is not None:
            if not is_stale(current, stale_after=stale_after):
                raise LockHeld(current)
            conn.execute("DELETE FROM locks WHERE key = ?", (key,))
        conn.execute(
            "INSERT INTO locks (key, owner, pid, hostname, run_id, acquired_at, heartbeat_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, info.owner, info.pid, info.hostname, run_id, now, now),
        )
    return Lock(db, info)
