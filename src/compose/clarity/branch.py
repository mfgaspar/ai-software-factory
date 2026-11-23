"""The clarity branch and its worktree, ``$COMPOSE_HOME/worktrees/<repo>/clarity``.

Clarity runs work on their own branch (config ``clarity.branch``, default ``clarity``),
created from the repo's default branch. Compose commits only the paths clarity owns
(:data:`CLARITY_PATHS`) there, and fast-forwards the default branch to it after a PASS.
It never pushes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from compose.core.config import ClarityConfig
from compose.core.home import Home
from compose.core.models import Repo
from compose.repos import git
from compose.runner.errors import RunError

WORKTREE_NAME = "clarity"
DEFAULT_BRANCH = ClarityConfig().branch
CLARITY_PATHS = (".clarity", ".compose/memory/constitution.md")
GUARDED_PATHS = (".clarity", ".compose/memory")  # must be clean in a checked-out default branch


@dataclass(frozen=True)
class MergeOutcome:
    merged: bool
    pending_reason: str | None = None


def worktree_path(home: Home, repo: Repo) -> Path:
    return home.worktrees / repo.name / WORKTREE_NAME


def default_branch(repo: Repo) -> str:
    return repo.default_branch or git.default_branch(Path(repo.path))


def ensure_worktree(
    home: Home, repo: Repo, *, branch: str = DEFAULT_BRANCH, update: bool = True
) -> Path:
    """Return the clarity worktree, creating the branch and/or worktree as needed.

    With ``update``, the default branch is merged into the clarity branch first. A
    conflict aborts the merge (both branches stay as they were) and raises
    :class:`RunError` naming the conflicted files.
    """
    repo_path = Path(repo.path)
    path = worktree_path(home, repo).resolve()
    base = default_branch(repo)
    try:
        if not git.branch_exists(repo_path, branch):
            git.create_branch(repo_path, branch, base)
        _checkout(repo_path, path, branch)
    except git.GitError as exc:
        raise RunError(f"Could not set up the clarity worktree {path}: {exc}") from exc
    if update:
        update_from_default(path, base)
    return path


def _checkout(repo_path: Path, path: Path, branch: str) -> None:
    git.worktree_prune(repo_path)  # forget worktrees whose folders are gone
    for wt in git.worktree_list(repo_path):
        if wt.branch != branch:
            continue
        if wt.path == path and path.is_dir():
            return
        raise RunError(
            f"Branch {branch} is checked out in {wt.path}; switch that checkout"
            " to another branch so compose can use it for clarity runs"
        )
    if path.exists():
        raise RunError(f"{path} exists but is not the worktree for {branch}")
    git.worktree_add(repo_path, path, branch)


def update_from_default(workdir: Path, base: str) -> None:
    """Merge the default branch ``base`` into the clarity branch checked out in ``workdir``."""
    if git.is_ancestor(workdir, base, "HEAD"):
        return
    try:
        git.merge(workdir, base)
    except git.GitError as exc:
        conflicts = git.conflicted_files(workdir)
        git.merge_abort(workdir)
        if conflicts:
            raise RunError(
                f"Merging {base} into the clarity branch conflicts in: {', '.join(conflicts)}."
                f" Resolve it in {workdir} (git merge {base}), then try again"
            ) from exc
        raise RunError(f"Could not merge {base} into the clarity branch: {exc}") from exc


def commit_paths(workdir: Path, message: str) -> str | None:
    """Commit changes under :data:`CLARITY_PATHS` only; return the new sha, or None."""
    paths = [
        p
        for p in CLARITY_PATHS
        if ((workdir / p).exists() or git.is_tracked(workdir, p)) and not git.is_ignored(workdir, p)
    ]
    if not paths or not git.changed_paths(workdir, *paths):
        return None
    git.git(workdir, "add", "-A", "--", *paths)
    if not git.changed_paths(workdir, *paths):
        return None
    git.git(workdir, "commit", "--quiet", "--no-verify", "-m", message, "--", *paths)
    return git.rev_parse(workdir, "HEAD")


def merge_into_default(repo: Repo, workdir: Path) -> MergeOutcome:
    """Fast-forward the default branch to the clarity branch checked out in ``workdir``.

    When the default branch moved, it's merged into the clarity branch first and the
    outcome is pending: the caller must re-check the verdict on the merged content.
    """
    repo_path = Path(repo.path)
    base = default_branch(repo)
    branch = git.current_branch(workdir)
    if branch is None:
        return MergeOutcome(False, f"{workdir} is not on a branch")
    if not git.is_ancestor(repo_path, base, branch):
        try:
            update_from_default(workdir, base)
        except RunError as exc:
            return MergeOutcome(False, str(exc))
        return MergeOutcome(False, "default branch moved; re-validate")
    target = git.rev_parse(repo_path, branch)
    old = git.rev_parse(repo_path, base)
    if target == old:
        return MergeOutcome(True)
    checkout = next((wt for wt in git.worktree_list(repo_path) if wt.branch == base), None)
    if checkout is None:
        git.update_ref(repo_path, base, target, old)
        return MergeOutcome(True)
    dirty = git.changed_paths(checkout.path, *GUARDED_PATHS)
    if dirty:
        return MergeOutcome(
            False,
            f"{base} is checked out in {checkout.path} with uncommitted changes under"
            f" .clarity/ or .compose/memory/ ({', '.join(dirty)}); commit or stash them,"
            " then run compose clarity merge",
        )
    try:
        git.merge(checkout.path, branch, ff_only=True)
    except git.GitError as exc:
        return MergeOutcome(False, f"Could not fast-forward {base} in {checkout.path}: {exc}")
    return MergeOutcome(True)
