from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from typer.testing import Result

from compose import __version__


def test_version(cli: Callable[..., Result]) -> None:
    result = cli("--version")
    assert result.exit_code == 0
    assert result.output.strip() == f"compose {__version__}"


def test_no_args_shows_help(cli: Callable[..., Result]) -> None:
    result = cli()
    assert "Usage" in result.output


def test_fixtures_are_isolated(
    compose_home: Path, git_repo: Path, run_git: Callable[..., str]
) -> None:
    assert os.environ["COMPOSE_HOME"] == str(compose_home)
    assert Path.home() / ".compose" != compose_home
    assert run_git(git_repo, "branch", "--show-current") == "main"
    assert run_git(git_repo, "log", "--oneline").count("\n") == 0
