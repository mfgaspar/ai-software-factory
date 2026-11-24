"""One git worktree per feature for workflow runs, under ``$COMPOSE_HOME/worktrees``."""

from __future__ import annotations

from pathlib import Path

from compose.core import store
from compose.core.db import Database
from compose.core.home import Home
from compose.core.models import Feature, Repo
from compose.repos import git


class WorktreeError(Exception):
    """A feature worktree cannot be created."""


def worktree_path(home: Home, repo: Repo, feature_name: str) -> Path:
    return home.worktrees / repo.name / feature_name


def ensure_feature_worktree(db: Database, home: Home, repo: Repo, feature: Feature) -> Path:
    """Return the feature's worktree, creating the branch and/or worktree as needed.

    New branches start from the repo's default branch. A worktree whose folder was
    deleted is recreated from the branch.
    """
    repo_path = Path(repo.path)
    path = worktree_path(home, repo, feature.name).resolve()

    if not git.branch_exists(repo_path, feature.branch):
        base = repo.default_branch or git.default_branch(repo_path)
        git.create_branch(repo_path, feature.branch, base)

    git.worktree_prune(repo_path)  # forget worktrees whose folders are gone
    for wt in git.worktree_list(repo_path):
        if wt.branch != feature.branch:
            continue
        if wt.path == path and path.is_dir():
            break  # already in place
        raise WorktreeError(
            f"Branch {feature.branch} is checked out in {wt.path}; switch that checkout"
            " to another branch so compose can use it for runs"
        )
    else:
        if path.exists():
            raise WorktreeError(f"{path} exists but is not the worktree for {feature.branch}")
        git.worktree_add(repo_path, path, feature.branch)

    if feature.worktree_path != str(path):
        feature.worktree_path = str(path)
        store.update(db, feature)
    return path


def commit_all(worktree: Path, message: str) -> str | None:
    """Commit every change in a feature worktree (what ``.gitignore`` and the engines'
    hidden files leave out stays out); return the new sha, or None when nothing changed."""
    if not git.changed_paths(worktree):
        return None
    git.git(worktree, "add", "-A")
    if not git.changed_paths(worktree):
        return None
    git.git(worktree, "commit", "--quiet", "--no-verify", "-m", message)
    return git.rev_parse(worktree, "HEAD")


def merge_into_default(repo: Repo, branch: str) -> str | None:
    """Fast-forward the repo's default branch to ``branch``, so a finished feature shows in
    the repo's own folder. Returns None when the default branch now holds the work, or the
    reason it doesn't.

    Only a fast-forward: when the default branch moved since the feature started, or its
    checkout has changes the merge would overwrite, nothing is merged. It never pushes.
    """
    repo_path = Path(repo.path)
    try:
        base = repo.default_branch or git.default_branch(repo_path)
        target, old = git.rev_parse(repo_path, branch), git.rev_parse(repo_path, base)
        if target == old or git.is_ancestor(repo_path, branch, base):
            return None
        if not git.is_ancestor(repo_path, base, branch):
            return f"{base} changed since the feature started"
        checkout = next((wt for wt in git.worktree_list(repo_path) if wt.branch == base), None)
        if checkout is None:
            git.update_ref(repo_path, base, target, old)
        else:
            git.merge(checkout.path, branch, ff_only=True)
    except git.GitError as exc:
        lines = [line.strip() for line in str(exc).splitlines() if line.strip()]
        return lines[-1] if lines else "git refused the merge"
    return None
