from __future__ import annotations

from pathlib import Path

import pytest

from compose.core import store
from compose.core.db import Database
from compose.core.home import Home
from compose.core.models import Run
from compose.repos import git, registry


def test_add_local_path_uses_repo_root(db: Database, home: Home, git_repo: Path) -> None:
    sub = git_repo / "src"
    sub.mkdir()
    repo = registry.add_repo(db, home, str(sub))
    assert repo.path == str(git_repo.resolve())
    assert repo.name == "repo"
    assert repo.default_branch == "main"
    assert repo.origin_url is None
    assert registry.list_repos(db) == [repo]


def test_add_twice_rejected(db: Database, home: Home, git_repo: Path) -> None:
    registry.add_repo(db, home, str(git_repo))
    with pytest.raises(registry.RepoError, match="already registered"):
        registry.add_repo(db, home, str(git_repo), name="other")


def test_name_conflict(db: Database, home: Home, git_repo: Path, bare_remote: str) -> None:
    registry.add_repo(db, home, str(git_repo), name="app")
    with pytest.raises(registry.RepoError, match="--name"):
        registry.add_repo(db, home, bare_remote, name="app")


def test_invalid_name(db: Database, home: Home, git_repo: Path) -> None:
    with pytest.raises(registry.RepoError, match="Invalid repo name"):
        registry.add_repo(db, home, str(git_repo), name="Bad Name")


def test_not_a_repo(db: Database, home: Home, tmp_path: Path) -> None:
    with pytest.raises(registry.RepoError, match="not a git working tree"):
        registry.add_repo(db, home, str(tmp_path))


def test_add_url_clones(db: Database, home: Home, bare_remote: str) -> None:
    repo = registry.add_repo(db, home, bare_remote)
    assert repo.name == "remote"
    assert Path(repo.path) == (home.repos / "remote").resolve()
    assert (Path(repo.path) / "README.md").exists()
    assert repo.origin_url == bare_remote
    assert repo.default_branch == "main"


def test_add_bad_url_cleans_up(db: Database, home: Home, tmp_path: Path) -> None:
    with pytest.raises(registry.RepoError, match="Cannot clone"):
        registry.add_repo(db, home, f"file://{tmp_path}/nope.git")
    assert not (home.repos / "nope").exists()
    assert registry.list_repos(db) == []


@pytest.mark.parametrize(
    ("source", "is_url", "name"),
    [
        ("https://github.com/acme/web-app.git", True, "web-app"),
        ("git@github.com:acme/Api.git", True, "api"),
        ("ssh://git@host/x/y", True, "y"),
        ("file:///tmp/r.git", True, "r"),
        ("/home/me/code/thing", False, "thing"),
        ("./relative", False, "relative"),
    ],
)
def test_url_detection(source: str, is_url: bool, name: str) -> None:
    assert registry.is_url(source) is is_url
    assert registry.name_from_source(source) == name


def test_find_and_resolve(db: Database, home: Home, git_repo: Path, tmp_path: Path) -> None:
    repo = registry.add_repo(db, home, str(git_repo))
    git.create_branch(git_repo, "001-x", "main")
    wt = tmp_path / "wt"
    git.worktree_add(git_repo, wt, "001-x")
    assert registry.find_repo_for_path(db, wt) == repo
    assert registry.find_repo_for_path(db, tmp_path) is None
    assert registry.resolve_repo(db, None, git_repo) == repo
    assert registry.resolve_repo(db, repo.id, tmp_path) == repo
    with pytest.raises(registry.RepoError, match="Not inside a registered repo"):
        registry.resolve_repo(db, None, tmp_path)
    with pytest.raises(registry.RepoError, match="No registered repo"):
        registry.get_repo(db, "ghost")


def test_remove_guards(db: Database, home: Home, git_repo: Path, bare_remote: str) -> None:
    local = registry.add_repo(db, home, str(git_repo))
    with pytest.raises(registry.RepoError, match="not cloned by compose"):
        registry.remove_repo(db, home, local.name, delete_clone=True)
    store.insert(db, Run(id="run_1", repo_id=local.id, workflow_id="w", workflow_version="1"))
    with pytest.raises(registry.RepoError, match="--force"):
        registry.remove_repo(db, home, local.name)
    registry.remove_repo(db, home, local.name, force=True)
    assert git_repo.exists()  # never deleted

    cloned = registry.add_repo(db, home, bare_remote)
    registry.remove_repo(db, home, cloned.name, delete_clone=True)
    assert not Path(cloned.path).exists()
    assert registry.list_repos(db) == []
