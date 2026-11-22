"""Files and lines changed between two snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from compose.core.models import FileStatus
from compose.repos.git import git

_DIFF = ("diff", "--no-ext-diff", "--no-textconv", "--no-color", "-M", "-z")


@dataclass(frozen=True)
class Change:
    path: str
    status: FileStatus
    old_path: str | None = None
    added: int | None = None  # None for binary files
    removed: int | None = None


@dataclass(frozen=True)
class ChangeSummary:
    files: int
    added: int
    removed: int

    @classmethod
    def of(cls, changes: list[Change]) -> ChangeSummary:
        return cls(
            files=len(changes),
            added=sum(c.added or 0 for c in changes),
            removed=sum(c.removed or 0 for c in changes),
        )


def _name_status(raw: str) -> list[tuple[FileStatus, str | None, str]]:
    parts = raw.split("\0")
    out: list[tuple[FileStatus, str | None, str]] = []
    i = 0
    while i < len(parts) and parts[i]:
        code = parts[i]
        status = FileStatus(code[0])
        if status in (FileStatus.RENAMED, FileStatus.COPIED):
            out.append((status, parts[i + 1], parts[i + 2]))
            i += 3
        else:
            out.append((status, None, parts[i + 1]))
            i += 2
    return out


def _numstat(raw: str) -> dict[str, tuple[int | None, int | None]]:
    parts = raw.split("\0")
    out: dict[str, tuple[int | None, int | None]] = {}
    i = 0
    while i < len(parts) and parts[i]:
        added, removed, path = parts[i].split("\t", 2)
        if path == "":  # rename/copy: old and new path follow
            path = parts[i + 2]
            i += 3
        else:
            i += 1
        out[path] = (
            None if added == "-" else int(added),
            None if removed == "-" else int(removed),
        )
    return out


def diff_trees(worktree: Path, before: str, after: str) -> list[Change]:
    """Per-file status and line counts between two tree objects, sorted by path."""
    if before == after:
        return []
    statuses = _name_status(git(worktree, *_DIFF, "--name-status", before, after))
    counts = _numstat(git(worktree, *_DIFF, "--numstat", before, after))
    changes = [
        Change(path, status, old, *counts.get(path, (None, None))) for status, old, path in statuses
    ]
    return sorted(changes, key=lambda c: c.path)
