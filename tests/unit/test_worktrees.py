from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from compose.core import store
from compose.core.db import Database
from compose.core.home import Home
from compose.core.models import Feature, Repo
from compose.repos import features, git, registry, worktrees


@pytest.fixture
def repo(db: Database, home: Home, git_repo: Path) -> Repo:
    return registry.add_repo(db, home, str(git_repo))


def test_creates_branch_from_default_and_worktree(
    db: Database, home: Home, repo: Repo, git_repo: Path, run_git: Callable[..., str]
) -> None:
    # The user's checkout is on another branch with an extra commit; the feature
    # must still start from the default branch.
    run_git(git_repo, "switch", "-q", "-c", "wip")
    (git_repo / "wip.txt").write_text("wip\n")
    run_git(git_repo, "add", "wip.txt")
    run_git(git_repo, "commit", "-q", "-m", "wip")

    feature = features.upsert_feature(db, repo, "001-login")
    path = worktrees.ensure_feature_worktree(db, home, repo, feature)

    assert path == (home.worktrees / "repo" / "001-login").resolve()
    assert run_git(path, "branch", "--show-current") == "001-login"
    assert not (path / "wip.txt").exists()
    assert run_git(path, "rev-parse", "HEAD") == run_git(git_repo, "rev-parse", "main")
    saved = store.get(db, Feature, feature.id)
    assert saved is not None and saved.worktree_path == str(path)


def test_reuses_existing(db: Database, home: Home, repo: Repo) -> None:
    feature = features.upsert_feature(db, repo, "001-login")
    first = worktrees.ensure_feature_worktree(db, home, repo, feature)
    (first / "note.txt").write_text("keep me\n")
    again = worktrees.ensure_feature_worktree(db, home, repo, feature)
    assert again == first
    assert (again / "note.txt").read_text() == "keep me\n"


def test_recreates_after_folder_deleted(db: Database, home: Home, repo: Repo) -> None:
    feature = features.upsert_feature(db, repo, "001-login")
    path = worktrees.ensure_feature_worktree(db, home, repo, feature)
    shutil.rmtree(path)
    again = worktrees.ensure_feature_worktree(db, home, repo, feature)
    assert again == path and (path / "README.md").exists()


def test_uses_existing_branch(db: Database, home: Home, repo: Repo, git_repo: Path) -> None:
    git.create_branch(git_repo, "002-existing", "main")
    tip = git.git(git_repo, "rev-parse", "002-existing")
    feature = features.upsert_feature(db, repo, "002-existing")
    path = worktrees.ensure_feature_worktree(db, home, repo, feature)
    assert git.git(path, "rev-parse", "HEAD") == tip


def test_branch_checked_out_in_user_checkout(
    db: Database, home: Home, repo: Repo, git_repo: Path
) -> None:
    features.create_feature(git_repo, "login")  # manual: user is now on 001-login
    feature = features.upsert_feature(db, repo, "001-login")
    with pytest.raises(worktrees.WorktreeError, match="is checked out in"):
        worktrees.ensure_feature_worktree(db, home, repo, feature)


def test_foreign_folder_in_the_way(db: Database, home: Home, repo: Repo) -> None:
    feature = features.upsert_feature(db, repo, "001-login")
    blocker = worktrees.worktree_path(home, repo, feature.name)
    blocker.mkdir(parents=True)
    with pytest.raises(worktrees.WorktreeError, match="is not the worktree"):
        worktrees.ensure_feature_worktree(db, home, repo, feature)
    assert git.branch_exists(Path(repo.path), "001-login")
