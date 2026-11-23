"""The clarity verdict: the validator's last line, recorded in ``.clarity/verdict.yml``.

``/clarity-validate`` ends with ``CLARITY: PASS`` or ``CLARITY: FAIL (<n> incomplete)``.
Anything else (no line, a malformed one) counts as FAIL with an unknown count. compose
records ``{result, incomplete, fingerprint, run_id, at}`` so a later check can tell whether
the verdict still describes the documents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from compose.repos import git
from compose.runner.state import atomic_write

VERDICT_FILE = ".clarity/verdict.yml"
Result = Literal["PASS", "FAIL"]
_LINE = re.compile(r"^CLARITY: (?:(PASS)|FAIL \((\d+) incomplete\))$")


@dataclass(frozen=True)
class Verdict:
    result: Result
    incomplete: int | None = 0

    @property
    def passed(self) -> bool:
        return self.result == "PASS"


@dataclass(frozen=True)
class Recorded:
    """A verdict as recorded in ``verdict.yml``."""

    verdict: Verdict
    fingerprint: str
    run_id: str | None
    at: str | None


def parse(text: str) -> Verdict:
    """The verdict in the last non-empty line of ``text``."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    match = _LINE.match(lines[-1]) if lines else None
    if match is None:
        return Verdict("FAIL", None)
    if match.group(1):
        return Verdict("PASS", 0)
    return Verdict("FAIL", int(match.group(2)))


def write(workdir: Path, verdict: Verdict, fingerprint: str, run_id: str | None) -> Path:
    """Write ``workdir/.clarity/verdict.yml`` and return its path."""
    path = workdir / VERDICT_FILE
    data = {
        "result": verdict.result,
        "incomplete": verdict.incomplete,
        "fingerprint": fingerprint,
        "run_id": run_id,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    atomic_write(path, yaml.safe_dump(data, sort_keys=False))
    return path


def from_text(text: str) -> Recorded | None:
    """A recorded verdict from ``verdict.yml``'s text, or None when it's malformed."""
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or data.get("result") not in ("PASS", "FAIL"):
        return None
    fingerprint = data.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        return None
    incomplete = data.get("incomplete")
    verdict = Verdict(data["result"], incomplete if isinstance(incomplete, int) else None)
    run_id, at = data.get("run_id"), data.get("at")
    return Recorded(
        verdict,
        fingerprint,
        str(run_id) if run_id is not None else None,
        str(at) if at is not None else None,
    )


def read_ref(root: Path, ref: str) -> Recorded | None:
    """The verdict committed on ``ref``, or None when it's missing or malformed."""
    proc = git.run_git(root, "show", f"{ref}:{VERDICT_FILE}", check=False)
    if proc.returncode != 0:
        return None
    return from_text(proc.stdout)
