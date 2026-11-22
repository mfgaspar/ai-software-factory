"""Shared fixtures. Tests never touch the real ~/.compose or the user's git config."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from compose.cli.app import app
from compose.core.db import Database, open_database
from compose.core.home import Home, ensure_home


@pytest.fixture(autouse=True)
def compose_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated COMPOSE_HOME for every test."""
    home = tmp_path / "compose-home"
    home.mkdir()
    monkeypatch.setenv("COMPOSE_HOME", str(home))
    # Keep git hermetic: ignore the user's global/system config.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("COMPOSE_FEATURE", raising=False)
    monkeypatch.delenv("COMPOSE_RUN_ID", raising=False)
    return home


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def run_git() -> Callable[..., str]:
    """Run git in a directory: run_git(path, "status")."""
    return _git


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one commit on `main`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "compose-test")
    _git(repo, "config", "user.email", "compose-test@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("# test repo\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


@pytest.fixture
def cli() -> Callable[..., Result]:
    """Invoke the compose CLI: cli("--version")."""
    runner = CliRunner()

    def invoke(*args: str) -> Result:
        return runner.invoke(app, list(args))

    return invoke


@pytest.fixture
def home(compose_home: Path) -> Home:
    return ensure_home()


@pytest.fixture
def db(home: Home) -> Iterator[Database]:
    database = open_database(home)
    yield database
    database.close()


@pytest.fixture
def bare_remote(git_repo: Path, tmp_path: Path) -> str:
    """A bare clone of git_repo, as a file:// URL (stands in for a hosted repo)."""
    bare = tmp_path / "remote.git"
    _git(tmp_path, "clone", "-q", "--bare", str(git_repo), str(bare))
    return f"file://{bare}"
