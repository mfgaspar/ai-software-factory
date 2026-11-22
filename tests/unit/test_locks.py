from __future__ import annotations

import subprocess
import sys
import time

import pytest

from compose.core import locks
from compose.core.db import Database


def test_acquire_and_release(db: Database) -> None:
    lock = locks.acquire(db, "feature:f1", run_id="run_1")
    info = locks.read_lock(db, "feature:f1")
    assert info is not None and info.run_id == "run_1"
    lock.release()
    assert locks.read_lock(db, "feature:f1") is None


def test_context_manager(db: Database) -> None:
    with locks.acquire(db, "k"):
        assert locks.read_lock(db, "k") is not None
    assert locks.read_lock(db, "k") is None


def test_second_acquire_fails(db: Database) -> None:
    with locks.acquire(db, "k", run_id="run_1"):
        with pytest.raises(locks.LockHeld) as err:
            locks.acquire(db, "k")
        assert "run_1" in str(err.value)


def test_independent_keys(db: Database) -> None:
    with (
        locks.acquire(db, locks.feature_lock_key("a")),
        locks.acquire(db, locks.feature_lock_key("b")),
    ):
        pass


def test_stale_by_dead_pid_is_reclaimed(db: Database) -> None:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    lock = locks.acquire(db, "k")
    with db.transaction() as conn:
        conn.execute("UPDATE locks SET pid = ? WHERE key = 'k'", (proc.pid,))
    new = locks.acquire(db, "k", run_id="run_2")
    info = locks.read_lock(db, "k")
    assert info is not None and info.run_id == "run_2"
    with pytest.raises(locks.LockLost):
        lock.heartbeat()
    lock.release()  # must not delete the new owner's row
    assert locks.read_lock(db, "k") is not None
    new.release()


def test_stale_by_old_heartbeat_is_reclaimed(db: Database) -> None:
    locks.acquire(db, "k")
    with db.transaction() as conn:
        conn.execute("UPDATE locks SET hostname = 'other-host', heartbeat_at = ?", (0.0,))
    locks.acquire(db, "k", stale_after=60).release()


def test_other_host_with_fresh_heartbeat_is_live(db: Database) -> None:
    locks.acquire(db, "k")
    with db.transaction() as conn:
        conn.execute("UPDATE locks SET hostname = 'other-host'")
    with pytest.raises(locks.LockHeld):
        locks.acquire(db, "k")


def test_heartbeat_and_keep_alive(db: Database) -> None:
    lock = locks.acquire(db, "k")
    before = locks.read_lock(db, "k")
    assert before is not None
    time.sleep(0.02)
    lock.heartbeat()
    after = locks.read_lock(db, "k")
    assert after is not None and after.heartbeat_at > before.heartbeat_at

    lock.keep_alive(interval=0.05)
    time.sleep(0.2)
    beat = locks.read_lock(db, "k")
    assert beat is not None and beat.heartbeat_at > after.heartbeat_at
    lock.release()
    assert locks.read_lock(db, "k") is None
