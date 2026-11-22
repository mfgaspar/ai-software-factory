"""Globally unique, time-sortable ids (ULID format, with a type prefix)."""

from __future__ import annotations

import os
import threading
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
_lock = threading.Lock()
_last_ms = -1
_last_rand = 0


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def ulid() -> str:
    """A 26-char ULID; monotonic within this process."""
    global _last_ms, _last_rand
    with _lock:
        now = time.time_ns() // 1_000_000
        if now <= _last_ms:
            now = _last_ms
            rand = (_last_rand + 1) & ((1 << 80) - 1)
        else:
            rand = int.from_bytes(os.urandom(10), "big")
        _last_ms, _last_rand = now, rand
    return _encode(now, 10) + _encode(rand, 16)


def new_id(prefix: str) -> str:
    """E.g. ``new_id("run")`` -> ``run_01JD...``."""
    return f"{prefix}_{ulid()}"
