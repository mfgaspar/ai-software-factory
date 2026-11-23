"""Thin wrapper around the ``git`` command line."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    """A git command failed."""

    def __init__(self, args: Sequence[str], returncode: int, stderr: str) -> None:
        detail = stderr.strip() or f"exit code {returncode}"
        super().__init__(f"git {' '.join(args)} failed: {detail}")
        self.args_ = list(args)
        self.returncode = returncode
        self.stderr = stderr


def run_git(
    cwd: Path,
    *args: str,
    check: bool = True,
    env: Mapping[str, str] | None = None,
    input_: str | None = None,
) -> subprocess.CompletedProcess[str]:
    full_env = None
    if env is not None:
        full_env = {**os.environ, **env}
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=full_env,
        input=input_,
    )
    if check and proc.returncode != 0:
        raise GitError(args, proc.returncode, proc.stderr)
    return proc


def git(cwd: Path, *args: str, env: Mapping[str, str] | None = None) -> str:
    """Run git and return stripped stdout; raise :class:`GitError` on failure."""
    return run_git(cwd, *args, env=env).stdout.strip()


def is_work_tree(path: Path) -> bool:
    if not path.is_dir():
        return False
    proc = run_git(path, "rev-parse", "--is-inside-work-tree", check=False)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def toplevel(path: Path) -> Path:
    """Root of the working tree containing ``path`` (a linked worktree's own root)."""
    return Path(git(path, "rev-parse", "--show-toplevel")).resolve()


def main_worktree(path: Path) -> Path:
    """Root of the main working tree, even when ``path`` is inside a linked worktree."""
    common = Path(git(path, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    return common.resolve().parent


def current_branch(path: Path) -> str | None:
    name = run_git(path, "branch", "--show-current", check=False).stdout.strip()
    return name or None


def branch_exists(repo: Path, name: str) -> bool:
    proc = run_git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{name}", check=False)
    return proc.returncode == 0


def local_branches(repo: Path) -> list[str]:
    out = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return [line for line in out.splitlines() if line]


def remote_branches(repo: Path) -> list[str]:
    """Remote branch names without the remote prefix (``origin/foo`` -> ``foo``)."""
    out = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/remotes")
    names = []
    for line in out.splitlines():
        if "/" in line and not line.endswith("/HEAD"):
            names.append(line.split("/", 1)[1])
    return names


def origin_url(repo: Path) -> str | None:
    proc = run_git(repo, "remote", "get-url", "origin", check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def default_branch(repo: Path) -> str:
    """Best guess at the repo's default branch."""
    proc = run_git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip().split("/", 1)[-1]
    for candidate in ("main", "master", "trunk", "develop"):
        if branch_exists(repo, candidate):
            return candidate
    branch = current_branch(repo)
    if branch:
        return branch
    raise GitError(["symbolic-ref"], 1, f"cannot determine default branch of {repo}")


def create_branch(repo: Path, name: str, start: str) -> None:
    git(repo, "branch", name, start)


def switch_new_branch(repo: Path, name: str) -> None:
    """Create ``name`` at HEAD and switch to it (keeps local changes)."""
    git(repo, "switch", "-c", name)


def clone(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    git(dest.parent, "clone", "--quiet", url, str(dest))


@dataclass(frozen=True)
class WorktreeInfo:
    path: Path
    head: str | None
    branch: str | None  # short name; None when detached
    prunable: bool


def worktree_list(repo: Path) -> list[WorktreeInfo]:
    out = git(repo, "worktree", "list", "--porcelain")
    items: list[WorktreeInfo] = []
    for block in out.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            fields[key] = value
        if "worktree" not in fields:
            continue
        branch = fields.get("branch")
        items.append(
            WorktreeInfo(
                path=Path(fields["worktree"]).resolve(),
                head=fields.get("HEAD"),
                branch=branch.removeprefix("refs/heads/") if branch else None,
                prunable="prunable" in fields,
            )
        )
    return items


def worktree_add(repo: Path, path: Path, branch: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    git(repo, "worktree", "add", "--quiet", str(path), branch)


def worktree_prune(repo: Path) -> None:
    git(repo, "worktree", "prune")


def rev_parse(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    proc = run_git(repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False)
    return proc.returncode == 0


def conflicted_files(worktree: Path) -> list[str]:
    out = git(worktree, "diff", "--name-only", "--diff-filter=U")
    return [line for line in out.splitlines() if line]


def merge(worktree: Path, ref: str, *, ff_only: bool = False) -> None:
    """Merge ``ref`` into the branch checked out in ``worktree``."""
    git(worktree, "merge", "--quiet", "--ff-only" if ff_only else "--no-edit", ref)


def merge_abort(worktree: Path) -> None:
    run_git(worktree, "merge", "--abort", check=False)


def changed_paths(worktree: Path, *paths: str) -> list[str]:
    """Uncommitted changes (staged, unstaged or untracked) under ``paths``."""
    out = run_git(worktree, "status", "--porcelain", "--", *paths).stdout
    return [line[3:] for line in out.splitlines() if line]


def is_tracked(worktree: Path, path: str) -> bool:
    return bool(git(worktree, "ls-files", "--", path))


def is_ignored(worktree: Path, path: str) -> bool:
    return run_git(worktree, "check-ignore", "-q", "--", path, check=False).returncode == 0


def update_ref(repo: Path, branch: str, new: str, old: str) -> None:
    """Move ``branch`` to ``new``, only if it still points at ``old``."""
    git(repo, "update-ref", f"refs/heads/{branch}", new, old)


def user_name(path: Path) -> str | None:
    """The git user name configured for ``path`` (``user.name``), or None."""
    proc = run_git(path, "config", "user.name", check=False)
    return proc.stdout.strip() or None if proc.returncode == 0 else None
