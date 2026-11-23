"""The generated-from-clarity marker on ``.compose/memory/constitution.md``.

In a clarity repo the constitution is generated from the clarity documents, and its first
line records the clarity fingerprint it came from:
``<!-- generated-from-clarity: <fingerprint> -->``.
"""

from __future__ import annotations

import re
from pathlib import Path

from compose.repos import git
from compose.runner.state import atomic_write

CONSTITUTION_FILE = ".compose/memory/constitution.md"
_MARKER = re.compile(r"^<!-- generated-from-clarity: (\S*) -->$")


def marker(fingerprint: str) -> str:
    return f"<!-- generated-from-clarity: {fingerprint} -->"


def read_text(text: str) -> str | None:
    """The fingerprint stamped on ``text``'s first line, or None."""
    first = text.split("\n", 1)[0].rstrip("\r")
    match = _MARKER.match(first)
    return (match.group(1) or None) if match else None


def stamp(path: Path, fingerprint: str) -> None:
    """Add the marker as ``path``'s first line, replacing one that's already there."""
    text = path.read_text(encoding="utf-8")
    if _MARKER.match(text.split("\n", 1)[0].rstrip("\r")):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    atomic_write(path, f"{marker(fingerprint)}\n{text}")


def read_ref(root: Path, ref: str) -> str | None:
    """The fingerprint stamped on the constitution committed on ``ref``, or None."""
    proc = git.run_git(root, "show", f"{ref}:{CONSTITUTION_FILE}", check=False)
    if proc.returncode != 0:
        return None
    return read_text(proc.stdout)
