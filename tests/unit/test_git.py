from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from compose.repos import git


def test_is_work_tree(git_repo: Path, tmp_path: Path) -> None:
    assert git.is_work_tree(git_repo)
    assert not git.is_work_tree(tmp_path / "missing")
    plain = tmp_path / "plain"
    plain.mkdir()
    assert not git.is_work_tree(plain)


def test_toplevel_from_subdir(git_repo: Path) -> None:
    sub = git_repo / "a" / "b"
    sub.mkdir(parents=True)
    assert git.toplevel(sub) == git_repo.resolve()


def test_main_worktree_from_linked_worktree(git_repo: Path, tmp_path: Path) -> None:
    git.create_branch(git_repo, "001-x", "main")
    wt = tmp_path / "wt"
    git.worktree_add(git_repo, wt, "001-x")
    assert git.toplevel(wt) == wt.resolve()
    assert git.main_worktree(wt) == git_repo.resolve()
    listed = {w.branch: w.path for w in git.worktree_list(git_repo)}
    assert listed["main"] == git_repo.resolve()
    assert listed["001-x"] == wt.resolve()


def test_branches(git_repo: Path) -> None:
    assert git.current_branch(git_repo) == "main"
    assert not git.branch_exists(git_repo, "dev")
    git.create_branch(git_repo, "dev", "main")
    assert git.branch_exists(git_repo, "dev")
    assert sorted(git.local_branches(git_repo)) == ["dev", "main"]


def test_default_branch_local(git_repo: Path, run_git: Callable[..., str]) -> None:
    assert git.default_branch(git_repo) == "main"
    run_git(git_repo, "branch", "-m", "main", "work")
    assert git.default_branch(git_repo) == "work"  # falls back to the current branch


def test_clone_and_remote_info(bare_remote: str, tmp_path: Path) -> None:
    dest = tmp_path / "clone"
    git.clone(bare_remote, dest)
    assert git.origin_url(dest) == bare_remote
    assert git.default_branch(dest) == "main"
    assert "main" in git.remote_branches(dest)


def test_origin_url_none(git_repo: Path) -> None:
    assert git.origin_url(git_repo) is None


def test_git_error_message(git_repo: Path) -> None:
    with pytest.raises(git.GitError) as err:
        git.git(git_repo, "rev-parse", "--verify", "nope")
    assert "git rev-parse --verify nope failed" in str(err.value)
