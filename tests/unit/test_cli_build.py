"""``compose build``: the default workflow on a new feature, after the pre-run check."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import Result

from compose.cli import runs
from compose.engines.fake import FakeEngine
from compose.engines.registry import EngineRegistry
from compose.repos import git
from tests.unit.clarity_helpers import foundation

FEATURE = """
workflow: {id: feat, name: Feat, version: 1.0.0}
inputs:
  level: {type: string, default: low}
  goal: {type: string, required: true}
steps:
  - {id: build, type: shell, run: "printf '%s\\n' '{{ inputs.goal }}' > goal.txt"}
"""
NO_TEXT = """
workflow: {id: nums, name: Nums, version: 1.0.0}
inputs:
  count: {type: number, required: true}
steps:
  - {id: build, type: shell, run: echo built}
"""


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, compose_home: Path, tmp_path: Path) -> Path:
    """A fake engine, and the FEATURE workflow as the configured default; returns its path."""
    engine = FakeEngine()
    monkeypatch.setattr(runs, "engine_registry", lambda: EngineRegistry({"fake": engine}))
    path = tmp_path / "feat.yml"
    path.write_text(FEATURE)
    (compose_home / "config.yml").write_text(
        f"defaults: {{engine: fake, workflow: {json.dumps(str(path))}}}\n"
    )
    return path


@pytest.fixture
def repo(cli: Callable[..., Result], git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    assert cli("repo", "add", str(git_repo)).exit_code == 0
    monkeypatch.chdir(git_repo)
    return git_repo


def as_json(result: Result) -> Any:
    assert result.output.strip(), result.output
    return json.loads(result.output)


def test_build_without_clarity_warns_and_runs(
    cli: Callable[..., Result], fake: Path, repo: Path
) -> None:
    result = cli("build", "a todo app", "--json")
    assert result.exit_code == 0, result.output
    data = as_json(result)
    assert data["workflow_id"] == "feat" and data["status"] == "completed"
    assert data["inputs"] == {"level": "low", "goal": "a todo app"}
    assert data["feature"] == "001-todo-app"
    assert len(data["warnings"]) == 1 and "No clarity foundation" in data["warnings"][0]
    assert (Path(data["worktree"]) / "goal.txt").read_text() == "a todo app\n"

    text = cli("build", "another thing", "--no-interactive")
    assert text.exit_code == 0, text.output
    assert "warning: No clarity foundation" in text.output


def test_build_takes_inputs_and_another_workflow(
    cli: Callable[..., Result], fake: Path, repo: Path, tmp_path: Path
) -> None:
    other = tmp_path / "other.yml"
    other.write_text(FEATURE.replace("id: feat", "id: other"))
    result = cli("build", "notes", "--workflow", str(other), "-i", "level=high", "--json")
    assert result.exit_code == 0, result.output
    data = as_json(result)
    assert data["workflow_id"] == "other"
    assert data["inputs"] == {"level": "high", "goal": "notes"}


def test_build_needs_a_required_text_input(
    cli: Callable[..., Result], fake: Path, repo: Path, tmp_path: Path
) -> None:
    path = tmp_path / "nums.yml"
    path.write_text(NO_TEXT)
    result = cli("build", "a thing", "--workflow", str(path))
    assert result.exit_code == 1
    assert "no required string input" in result.output
    clash = cli("build", "a thing", "-i", "goal=other")
    assert clash.exit_code == 1 and "build description" in clash.output


def test_build_with_clarity_not_passing_exits_1_and_creates_no_run(
    cli: Callable[..., Result], fake: Path, repo: Path
) -> None:
    git.git(repo, "branch", "clarity")
    result = cli("build", "a todo app", "--json")
    assert result.exit_code == 1
    assert "hasn't passed yet" in result.output and "Fix: compose clarity" in result.output
    assert as_json(cli("status", "--json")) == []


def test_build_with_a_current_pass_runs(cli: Callable[..., Result], fake: Path, repo: Path) -> None:
    foundation(repo)
    result = cli("build", "a todo app", "--json")
    assert result.exit_code == 0, result.output
    data = as_json(result)
    assert data["status"] == "completed" and data["warnings"] == []


def test_run_json_has_the_warnings(
    cli: Callable[..., Result], fake: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runs, "spawn", lambda home, run_id, cwd: 4242)
    result = cli("run", str(fake), "-i", "goal=a todo app", "--json")
    assert result.exit_code == 0, result.output
    assert "No clarity foundation" in as_json(result)["warnings"][0]
    detached = cli("run", str(fake), "-i", "goal=bg", "--detach", "--json")
    assert detached.exit_code == 0, detached.output
    assert as_json(detached)["pid"] == 4242
    assert "No clarity foundation" in as_json(detached)["warnings"][0]
