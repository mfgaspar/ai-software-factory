"""A run's event log (``log.jsonl``) as pages or as a Server-Sent Events stream.

Each event gets ``seq``, its 1-based line number in the log, which is also the SSE event
id: a client that reconnects with ``Last-Event-ID`` (or ``after``) misses nothing. The
log is written by whichever process executes the run, so this works for runs started by
the CLI too.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from compose.core.db import Database

POLL_SECONDS = 0.25
HEARTBEAT_SECONDS = 15.0
ACTIVE = ("created", "running")


def _parse(line: str, seq: int) -> dict[str, Any]:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        event = {"type": "unreadable", "line": line}
    return {"seq": seq, **event}


def read(path: Path, after: int = 0, limit: int = 500) -> list[dict[str, Any]]:
    """Events with ``seq > after``, at most ``limit``."""
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open() as fh:
        for seq, line in enumerate(fh, start=1):
            if seq <= after or not line.endswith("\n"):
                continue
            out.append(_parse(line, seq))
            if len(out) >= limit:
                break
    return out


def _status(db: Database, run_id: str) -> str | None:
    row = db.conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
    return None if row is None else str(row[0])


def _sse(event: dict[str, Any]) -> str:
    data = json.dumps(event, default=str)
    return f"id: {event['seq']}\nevent: {event.get('type', 'message')}\ndata: {data}\n\n"


async def stream(
    db: Database, run_id: str, path: Path, after: int = 0, *, poll: float = POLL_SECONDS
) -> AsyncIterator[str]:
    """Send events as they are written; finish with an ``end`` event once the run is no
    longer created or running (completed, paused, failed or aborted)."""
    seq = 0
    offset = 0
    pending = ""
    idle = 0.0
    stopping = False
    while True:
        status = await asyncio.to_thread(_status, db, run_id)
        sent = False
        if path.exists():
            with path.open() as fh:
                fh.seek(offset)
                chunk = fh.read()
                offset = fh.tell()
            pending += chunk
            *lines, pending = pending.split("\n")
            for line in lines:
                seq += 1
                if seq > after and line:
                    yield _sse(_parse(line, seq))
                    sent = True
        if status not in ACTIVE:
            if stopping:  # read once more after the status changed: nothing is left
                end = json.dumps({"run_id": run_id, "status": status})
                yield f"event: end\ndata: {end}\n\n"
                return
            stopping = True  # the final event is logged just after the status changes
        else:
            stopping = False
        idle = 0.0 if sent else idle + poll
        if idle >= HEARTBEAT_SECONDS:
            idle = 0.0
            yield ": keep-alive\n\n"
        await asyncio.sleep(poll)
