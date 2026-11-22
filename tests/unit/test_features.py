from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from compose.core.db import Database
from compose.core.home import Home
from compose.repos import features, git, registry


@pytest.mark.parametrize(
    ("text", "slug"),
    [
        ("Add user authentication with OAuth", "add-user-authentication-oauth"),
        ("I want to build a photo album app", "build-photo-album-app"),
        ("Café menu", "cafe-menu"),
        ("the a an", "the-a-an"),  # only stopwords: keep them
        ("!!!", "feature"),
        ("user-auth", "user-auth"),
    ],
)
def test_slugify(text: str, slug: str) -> None:
    assert features.slugify(text) == slug


def test_parse_and_format() -> None:
    assert features.format_name(7, "x-y") == "007-x-y"
    assert features.parse_name("012-user-auth") == (12, "user-auth")
    assert features.parse_name("1234-big") == (1234, "big")
    assert features.parse_name("main") is None
    assert features.parse_name("12-short") is None


def test_next_number_uses_branches_and_dirs(git_repo: Path) -> None:
    assert features.next_number(git_repo) == 1
    git.create_branch(git_repo, "001-a", "main")
    git.create_branch(git_repo, "005-b", "main")
    assert features.next_number(git_repo) == 6
    (git_repo / "specs" / "007-c").mkdir(parents=True)
    (git_repo / "specs" / "notes").mkdir()
    assert features.next_number(git_repo) == 8


def test_next_number_sees_remote_branches(
    git_repo: Path, bare_remote: str, run_git: Callable[..., str]
) -> None:
    run_git(git_repo, "remote", "add", "origin", bare_remote)
    run_git(git_repo, "push", "-q", "origin", "main:009-remote-only")
    run_git(git_repo, "fetch", "-q", "origin")
    assert features.next_number(git_repo) == 10


def test_create_feature_manual(git_repo: Path) -> None:
    paths, created = features.create_feature(git_repo, "Add photo albums")
    assert created
    assert paths.name == "001-add-photo-albums"
    assert git.current_branch(git_repo) == "001-add-photo-albums"
    assert paths.feature_dir == git_repo.resolve() / "specs" / "001-add-photo-albums"
    assert paths.feature_dir.is_dir()
    assert paths.spec_file.name == "spec.md"
    assert paths.constitution_file == git_repo.resolve() / ".compose/memory/constitution.md"

    second, _ = features.create_feature(git_repo, "ignored", short_name="Search", switch=False)
    assert second.name == "002-search"
    assert git.current_branch(git_repo) == "001-add-photo-albums"
    assert git.branch_exists(git_repo, "002-search")


def test_create_feature_inside_run_is_noop(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(features.FEATURE_ENV, "004-run-feature")
    paths, created = features.create_feature(git_repo, "Something else")
    assert not created
    assert paths.name == "004-run-feature"
    assert git.current_branch(git_repo) == "main"
    assert not (git_repo / "specs").exists()


def test_resolve_current(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(features.FeatureError, match="not a feature branch"):
        features.resolve_current(git_repo)
    features.create_feature(git_repo, "login")
    assert features.resolve_current(git_repo / "specs").name == "001-login"
    monkeypatch.setenv(features.FEATURE_ENV, "003-other")
    assert features.resolve_current(git_repo).name == "003-other"
    monkeypatch.setenv(features.FEATURE_ENV, "bad")
    with pytest.raises(features.FeatureError, match="not a feature name"):
        features.resolve_current(git_repo)


def test_resolve_outside_git(tmp_path: Path) -> None:
    with pytest.raises(features.FeatureError, match="not inside a git working tree"):
        features.resolve_current(tmp_path)


def test_list_features(git_repo: Path) -> None:
    git.create_branch(git_repo, "002-b", "main")
    (git_repo / "specs" / "001-a").mkdir(parents=True)
    (git_repo / "specs" / "002-b").mkdir()
    items = features.list_features(git_repo)
    assert [(i.name, i.has_branch, i.has_dir) for i in items] == [
        ("001-a", False, True),
        ("002-b", True, True),
    ]


def test_upsert_feature(db: Database, home: Home, git_repo: Path) -> None:
    repo = registry.add_repo(db, home, str(git_repo))
    first = features.upsert_feature(db, repo, "003-user-auth")
    assert (first.number, first.slug, first.branch) == (3, "user-auth", "003-user-auth")
    assert features.upsert_feature(db, repo, "003-user-auth") == first
    with pytest.raises(features.FeatureError):
        features.upsert_feature(db, repo, "nope")
