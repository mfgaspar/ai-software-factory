from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import Result

from compose.core import store
from compose.core.db import open_database
from compose.core.home import ensure_home
from compose.core.models import Feature


def _json(result: Result) -> object:
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_repo_add_list_remove(cli: Callable[..., Result], git_repo: Path) -> None:
    added = _json(cli("repo", "add", str(git_repo), "--name", "app", "--json"))
    assert isinstance(added, dict) and added["name"] == "app"
    listed = _json(cli("repo", "list", "--json"))
    assert isinstance(listed, list) and [r["name"] for r in listed] == ["app"]
    result = cli("repo", "remove", "app")
    assert result.exit_code == 0
    assert _json(cli("repo", "list", "--json")) == []


def test_repo_errors_are_one_line(cli: Callable[..., Result], tmp_path: Path) -> None:
    result = cli("repo", "add", str(tmp_path))
    assert result.exit_code == 1
    assert "error:" in result.output and "not a git working tree" in result.output
    assert "Traceback" not in result.output


def test_feature_new_and_paths(
    cli: Callable[..., Result], git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    assert cli("repo", "add", ".").exit_code == 0
    created = _json(cli("feature", "new", "Add", "photo", "albums", "--json"))
    assert isinstance(created, dict)
    assert created["name"] == "001-add-photo-albums" and created["created"] is True
    assert Path(str(created["feature_dir"])).is_dir()

    paths = _json(cli("feature", "paths", "--json"))
    assert isinstance(paths, dict) and paths["spec_file"] == created["spec_file"]

    listed = _json(cli("feature", "list", "--json"))
    assert isinstance(listed, list) and listed[0]["name"] == "001-add-photo-albums"

    shown = _json(cli("feature", "show", "001-add-photo-albums", "--json"))
    assert isinstance(shown, dict) and shown["branch_exists"] is True
    assert shown["files"] == {"spec": False, "plan": False, "tasks": False}

    # Recorded in the database because the repo is registered.
    db = open_database(ensure_home())
    names = [f.name for f in store.select(db, Feature)]
    db.close()
    assert names == ["001-add-photo-albums"]


def test_feature_new_inside_run(
    cli: Callable[..., Result], git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    monkeypatch.setenv("COMPOSE_FEATURE", "005-from-run")
    created = _json(cli("feature", "new", "whatever", "--json"))
    assert isinstance(created, dict)
    assert created["name"] == "005-from-run" and created["created"] is False


def test_feature_paths_not_on_feature(
    cli: Callable[..., Result], git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    result = cli("feature", "paths", "--json")
    assert result.exit_code == 1
    assert "not a feature branch" in result.output
