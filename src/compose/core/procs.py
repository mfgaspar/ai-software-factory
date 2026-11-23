"""Process handling that works on Linux, macOS and Windows.

compose starts process groups (shell steps, ``claude -p``, detached runs) so it can stop a
whole tree later, and checks whether a lock's owner is still alive. POSIX does both with
sessions and signals; Windows needs process-group creation flags, ``taskkill`` and the
Win32 API (``os.kill(pid, 0)`` there would send a Ctrl+C instead of probing).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

WINDOWS = sys.platform == "win32"


def group_kwargs() -> dict[str, Any]:
    """Popen/asyncio arguments that start the child in a process group of its own."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def detached_kwargs() -> dict[str, Any]:
    """Arguments for a child that outlives the parent and its console."""
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        return {"creationflags": flags}
    return {"start_new_session": True}


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


def _windows_pid_alive(pid: int) -> bool:  # pragma: no cover - Windows only
    if sys.platform != "win32":
        raise OSError("Windows only")
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    query_limited_information = 0x1000
    still_active = 259
    access_denied = 5
    handle = kernel32.OpenProcess(query_limited_information, False, pid)
    if not handle:
        return bool(ctypes.get_last_error() == access_denied)  # denied: it exists
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return bool(code.value == still_active)
    finally:
        kernel32.CloseHandle(handle)


def signal_tree(pid: int, *, force: bool) -> None:
    """Ask a process group to stop (``force``: kill it). Missing processes are ignored."""
    if sys.platform == "win32":  # pragma: no cover - Windows only
        command = ["taskkill", "/PID", str(pid), "/T"] + (["/F"] if force else [])
        with suppress(OSError):
            subprocess.run(command, capture_output=True, check=False, timeout=30)
        return
    with suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)


async def stop_tree(proc: asyncio.subprocess.Process, timeout: float) -> None:
    """Stop gently, then by force, waiting up to ``timeout`` seconds for each."""
    for force in (False, True):
        if proc.returncode is not None:
            return
        signal_tree(proc.pid, force=force)
        try:
            await asyncio.wait_for(proc.wait(), timeout)
            return
        except TimeoutError:
            continue


def posix_shell() -> str | None:
    """On Windows, the ``sh`` that shell steps run under (Git for Windows ships one)."""
    found = shutil.which("sh")
    if found:
        return found
    git = shutil.which("git")
    if git:  # ...\Git\cmd\git.exe -> ...\Git\bin\sh.exe
        candidate = Path(git).resolve().parent.parent / "bin" / "sh.exe"
        if candidate.is_file():
            return str(candidate)
    return None


async def start_shell(command: str, **kwargs: Any) -> asyncio.subprocess.Process:
    """Run ``command`` the way workflows are written: with ``sh`` on every platform.

    On Windows without an ``sh``, falls back to ``cmd.exe``.
    """
    if sys.platform == "win32":  # pragma: no cover - Windows only
        sh = posix_shell()
        if sh is not None:
            return await asyncio.create_subprocess_exec(sh, "-c", command, **kwargs)
    return await asyncio.create_subprocess_shell(command, **kwargs)
