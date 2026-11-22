"""Snapshots of a worktree as git tree objects, without commits or index changes."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from compose.repos.git import git, run_git

# compose's own scratch space inside a worktree; never part of a step's changes
EXCLUDED = (".compose/runs", ".compose/tmp")


def _git_path(worktree: Path, name: str) -> Path:
    path = Path(git(worktree, "rev-parse", "--git-path", name))
    return path if path.is_absolute() else worktree / path


def snapshot(worktree: Path) -> str:
    """Record the worktree (tracked and untracked files, minus ignored ones) as a tree.

    Works on a copy of the real index, so git's stat cache keeps it fast and the real
    index is never touched.
    """
    fd, name = tempfile.mkstemp(prefix="compose-index-")
    os.close(fd)
    index = Path(name)
    try:
        real = _git_path(worktree, "index")
        if real.exists():
            shutil.copyfile(real, index)
        else:
            index.unlink()
        env = {"GIT_INDEX_FILE": str(index)}
        if not real.exists():
            head = run_git(worktree, "rev-parse", "--verify", "-q", "HEAD^{commit}", check=False)
            if head.returncode == 0:
                git(worktree, "read-tree", "HEAD", env=env)
            else:
                git(worktree, "read-tree", "--empty", env=env)
        excludes = [f":(exclude){p}" for p in EXCLUDED]
        git(worktree, "add", "-A", "--", ".", *excludes, env=env)
        return git(worktree, "write-tree", env=env)
    finally:
        index.unlink(missing_ok=True)
