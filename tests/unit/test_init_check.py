from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import Result

from compose.engines.claude import install as installer


@pytest.fixture(autouse=True)
def _engine_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """Don't depend on this machine's Claude Code sign-in."""
    monkeypatch.setattr(installer, "check", lambda: [])


def status(repo: Path) -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


def test_init_fresh_repo(
    cli: Callable[..., Result], git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    result = cli("init", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["registered"] is True
    assert ".claude/skills/compose-specify/SKILL.md" in data["written"]
    assert ".claude/skills/compose/SKILL.md" in data["written"]
    assert ".compose/memory/constitution.md" in data["written"]
    assert ".compose/templates/compose/spec.md" in data["written"]
    assert ".gitignore" in data["written"]
    assert "/.compose/runs/" in (git_repo / ".gitignore").read_text()
    # nothing is committed: the files are new and untracked
    assert "?? .claude/" in status(git_repo)

    again = cli("init", "--json")
    assert again.exit_code == 0, again.output
    assert json.loads(again.output) | {"repo": None} == {
        "repo": None,
        "registered": False,
        "written": [],
    }

    text = cli("init")
    assert "Already registered" in text.output and "already in place" in text.output


def test_init_keeps_existing_constitution_and_gitignore(
    cli: Callable[..., Result], git_repo: Path
) -> None:
    (git_repo / ".compose" / "memory").mkdir(parents=True)
    (git_repo / ".compose" / "memory" / "constitution.md").write_text("# Ours\n")
    (git_repo / ".gitignore").write_text("node_modules/\n/.compose/runs/\n")
    result = cli("init", "--path", str(git_repo), "--json")
    assert result.exit_code == 0, result.output
    assert ".compose/memory/constitution.md" not in json.loads(result.output)["written"]
    assert (git_repo / ".compose/memory/constitution.md").read_text() == "# Ours\n"
    lines = (git_repo / ".gitignore").read_text().splitlines()
    assert lines[:2] == ["node_modules/", "/.compose/runs/"]
    assert lines.count("/.compose/runs/") == 1 and "/.compose/tmp/" in lines


def test_init_errors(cli: Callable[..., Result], git_repo: Path, tmp_path: Path) -> None:
    unknown = cli("init", "--path", str(git_repo), "--engine", "nope")
    assert unknown.exit_code == 1 and "Engine 'nope' is not available" in unknown.output

    plain = tmp_path / "plain"
    plain.mkdir()
    not_git = cli("init", "--path", str(plain))
    assert not_git.exit_code == 1 and "error:" in not_git.output

    assert cli("init", "--path", str(git_repo)).exit_code == 0
    worktree = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "other", str(worktree)], cwd=git_repo, check=True
    )
    nested = cli("init", "--path", str(worktree))
    assert nested.exit_code == 1 and "run compose init in the main checkout" in nested.output


def test_check(cli: Callable[..., Result], git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo)
    before = cli("check", "--json")
    assert before.exit_code == 1
    checks = {c["name"]: c for c in json.loads(before.output)["checks"]}
    assert checks["git"]["ok"] and checks["engine claude"]["ok"]
    assert not checks["repository registered"]["ok"]
    assert checks["repository registered"]["fix"] == "run `compose init` here"
    assert checks["repository initialized"]["required"] is False

    assert cli("init").exit_code == 0
    after = cli("check", "--json")
    assert after.exit_code == 0, after.output
    assert all(c["ok"] for c in json.loads(after.output)["checks"])
    assert "repository initialized" in cli("check").output


def test_check_engine_problems(
    cli: Callable[..., Result], git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    cli("init")
    monkeypatch.setattr(installer, "check", lambda: ["Claude Code is not signed in"])
    result = cli("check", "--json")
    assert result.exit_code == 1
    engine = next(c for c in json.loads(result.output)["checks"] if c["name"] == "engine claude")
    assert engine["detail"] == "Claude Code is not signed in"
    assert cli("check", "--engine", "nope").exit_code == 1


def test_check_outside_a_repo(
    cli: Callable[..., Result], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = cli("check", "--json")
    assert result.exit_code == 0  # a repo is only needed to run workflows
    repo = next(c for c in json.loads(result.output)["checks"] if c["name"] == "repository")
    assert not repo["ok"] and "compose repo add" in repo["fix"]
