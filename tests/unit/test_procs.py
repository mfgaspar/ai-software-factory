"""Cross-platform process helpers (exercised here on the POSIX branch)."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys

import pytest

from compose.core import procs

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX branch")


def test_pid_alive() -> None:
    assert procs.pid_alive(os.getpid())
    assert not procs.pid_alive(0) and not procs.pid_alive(-5)
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert not procs.pid_alive(child.pid)


def test_group_kwargs_start_a_new_session() -> None:
    assert procs.group_kwargs() == {"start_new_session": True}
    assert procs.detached_kwargs() == {"start_new_session": True}


async def test_stop_tree_kills_the_whole_group(tmp_path: object) -> None:
    # a shell that starts a grandchild; stopping the group must take both down
    proc = await procs.start_shell(
        "sleep 60 & echo $! ; wait",
        stdout=asyncio.subprocess.PIPE,
        **procs.group_kwargs(),
    )
    assert proc.stdout is not None
    grandchild = int((await proc.stdout.readline()).decode().strip())
    assert procs.pid_alive(grandchild)
    await procs.stop_tree(proc, timeout=5)
    assert proc.returncode is not None
    for _ in range(50):
        if not procs.pid_alive(grandchild):
            break
        await asyncio.sleep(0.1)
    assert not procs.pid_alive(grandchild)


def test_signal_tree_ignores_missing_processes() -> None:
    child = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    child.wait()
    procs.signal_tree(child.pid, force=True)  # no error
