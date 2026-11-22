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
