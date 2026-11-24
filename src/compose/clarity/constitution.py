"""The memory-index marker on ``.compose/memory/constitution.md``.

In a clarity repo the constitution is the index of ``.compose/memory/``, published from the
clarity documents (:mod:`compose.clarity.memory`). Its first line records the clarity
fingerprint it came from: ``<!-- memory-index: <fingerprint> -->``.

Before memory was published, a model wrote the constitution and compose stamped it
``<!-- generated-from-clarity: <fingerprint> -->``. That legacy marker no longer counts as
current: the repo has no memory files until clarity is validated again.
"""

from __future__ import annotations

import re
from pathlib import Path

from compose.repos import git

CONSTITUTION_FILE = ".compose/memory/constitution.md"
_MARKER = re.compile(r"^<!-- memory-index: (\S*) -->$")
_LEGACY_MARKER = re.compile(r"^<!-- generated-from-clarity: (\S*) -->$")


def marker(fingerprint: str) -> str:
    return f"<!-- memory-index: {fingerprint} -->"


def is_legacy(text: str) -> bool:
    """``text`` is a constitution a model generated from clarity, before memory existed."""
    return _LEGACY_MARKER.match(text.split("\n", 1)[0].rstrip("\r")) is not None


def read_text(text: str) -> str | None:
    """The fingerprint stamped on ``text``'s first line, or None."""
    first = text.split("\n", 1)[0].rstrip("\r")
    match = _MARKER.match(first)
    return (match.group(1) or None) if match else None


def read_ref(root: Path, ref: str) -> str | None:
    """The fingerprint stamped on the constitution committed on ``ref``, or None."""
    proc = git.run_git(root, "show", f"{ref}:{CONSTITUTION_FILE}", check=False)
    if proc.returncode != 0:
        return None
    return read_text(proc.stdout)
