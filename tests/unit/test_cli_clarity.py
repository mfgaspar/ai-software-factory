"""``compose clarity …`` over the fake engine standing in for the clarity skills."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import Result

from compose.cli import clarity as clarity_cli
from compose.cli import runs
from compose.engines.claude import install as installer
from compose.engines.fake import FakeEngine
from compose.engines.registry import EngineRegistry
from compose.repos import git
from tests.unit.clarity_helpers import QFILE, skills


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, compose_home: Path) -> FakeEngine:
    engine = FakeEngine(skills())
    monkeypatch.setattr(runs, "engine_registry", lambda: EngineRegistry({"fake": engine}))
    (compose_home / "config.yml").write_text("defaults: {engine: fake}\n")
    return engine


@pytest.fixture
def repo(cli: Callable[..., Result], git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    assert cli("repo", "add", str(git_repo)).exit_code == 0
    monkeypatch.chdir(git_repo)
    return git_repo


def as_json(result: Result) -> Any:
    assert result.output.strip(), result.output
    return json.loads(result.output)


def called(fake: FakeEngine) -> list[str]:
    return [f"{task.text} {task.args or ''}".strip() for task, _, _ in fake.calls]


def test_bare_sources_route_to_start(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path
) -> None:
    result = cli("clarity", "docs/prd.md", "docs/notes.md", "--mode", "auto", "--json")
    assert result.exit_code == 0, result.output
    data = as_json(result)
    assert data["workflow_id"] == "clarity"
    assert data["status"] == "completed"
    assert data["inputs"] == {"sources": "docs/prd.md docs/notes.md", "mode": "auto"}
    assert data["warnings"] == []
    assert called(fake)[0] == "clarity docs/prd.md docs/notes.md draft"


def test_an_option_first_also_routes_to_start(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path
) -> None:
    result = cli("clarity", "--mode", "auto", "--json")
    assert result.exit_code == 0, result.output
    assert as_json(result)["inputs"] == {"sources": "", "mode": "auto"}
    assert called(fake)[0] == "clarity draft"


def test_interactive_without_a_terminal_errors(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path
) -> None:
    result = cli("clarity", "docs/", "--mode", "interactive")
    assert result.exit_code == 1
    assert "needs a terminal" in result.output
    assert fake.calls == []


def test_interactive_starts_claude_in_the_worktree_then_validates(
    cli: Callable[..., Result],
    fake: FakeEngine,
    repo: Path,
    compose_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], Path]] = []

    def attached(argv: list[str], cwd: Path) -> int:
        calls.append((argv, cwd))
        return 0

    monkeypatch.setattr(clarity_cli, "_has_tty", lambda: True)
    monkeypatch.setattr(installer, "cli_path", lambda: "/opt/bin/claude")
    monkeypatch.setattr(clarity_cli, "_attached", attached)
    result = cli("clarity", "docs/", "--mode", "interactive", "--json")
    assert result.exit_code == 0, result.output
    worktree = (compose_home / "worktrees" / repo.name / "clarity").resolve()
    assert calls == [(["/opt/bin/claude", "/clarity docs/ interactive"], worktree)]
    assert (worktree / ".claude" / "skills" / "clarity" / "SKILL.md").is_file()
    data = as_json(result)
    assert data["workflow_id"] == "clarity-validate" and data["status"] == "completed"
    assert called(fake)[0] == "clarity-validate"


def test_pause_questions_answer_resumes_and_completes(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path
) -> None:
    main = git.rev_parse(repo, "main")
    started = cli("clarity", "docs/prd.md", "--no-interactive", "--json")
    assert started.exit_code == runs.EXIT_PAUSED, started.output
    run = as_json(started)
    assert [q["id"] for q in run["waiting"]["questions"]] == ["Q-001"]

    listed = cli("clarity", "questions", "--json")
    assert listed.exit_code == 0, listed.output
    assert [q["id"] for q in as_json(listed)] == ["Q-001"]

    first = cli("clarity", "answer", "Q-001", "3", "--json")
    assert first.exit_code == runs.EXIT_PAUSED, first.output  # apply raised the review
    data = as_json(first)
    assert data["id"] == run["id"]
    assert [q["id"] for q in data["waiting"]["questions"]] == ["Q-002"]

    second = cli("clarity", "answer", "Q-002", "confirm", "--json")
    assert second.exit_code == 0, second.output
    assert as_json(second)["status"] == "completed"
    assert git.rev_parse(repo, "main") != main  # PASS merged into the default branch

    worktree = Path(run["worktree"])
    answered = yaml.safe_load((worktree / QFILE).read_text())["questions"]
    assert {q["id"]: q["answered_by"] for q in answered} == {
        "Q-001": "compose-test",
        "Q-002": "compose-test",
    }
    status = as_json(cli("clarity", "status", "--json"))
    assert status["verdict"]["result"] == "PASS" and status["verdict"]["current"] is True
    assert status["build"]["ok"] is True


def test_no_resume_only_records(cli: Callable[..., Result], fake: FakeEngine, repo: Path) -> None:
    run = as_json(cli("clarity", "--no-interactive", "--json"))
    result = cli("clarity", "answer", "Q-001", "3", "--by", "pat", "--no-resume", "--json")
    assert result.exit_code == 0, result.output
    assert as_json(result) == {"recorded": ["Q-001"], "resumed_run": None, "pending": 0}
    detail = as_json(cli("status", run["id"], "--json"))
    assert detail["status"] == "paused"
    assert len(fake.calls) == 1


def test_an_invalid_answer_exits_1_with_the_reasons(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path
) -> None:
    run = as_json(cli("clarity", "--no-interactive", "--json"))
    result = cli("clarity", "answer", "Q-404", "yes")
    assert result.exit_code == 1
    assert "Q-404: no such question" in result.output
    empty = cli("clarity", "answer", "Q-001", "  ")
    assert empty.exit_code == 1
    assert "Q-001: the answer is empty" in empty.output
    assert as_json(cli("status", run["id"], "--json"))["status"] == "paused"


def test_answer_before_clarity_started_errors(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path
) -> None:
    result = cli("clarity", "answer", "Q-001", "3")
    assert result.exit_code == 1
    assert "no clarity questions" in result.output


def test_status_json(cli: Callable[..., Result], fake: FakeEngine, repo: Path) -> None:
    before = as_json(cli("clarity", "status", "--json"))
    assert before["started"] is False and before["verdict"] is None
    assert before["build"] == {"ok": True, "problems": [], "warnings": before["build"]["warnings"]}
    assert "No clarity foundation" in before["build"]["warnings"][0]

    assert cli("clarity", "--mode", "auto").exit_code == 0
    data = as_json(cli("clarity", "status", "--json"))
    assert data["started"] is True and data["branch"] == "clarity"
    assert data["worktree"].endswith("clarity")
    assert data["verdict"]["result"] == "FAIL" and data["verdict"]["current"] is True
    assert data["questions"] == {"pending": 1, "holding": 1, "ids": ["Q-001"]}
    assert data["constitution"]["current"] is True
    assert data["active_run"] is None
    assert data["build"]["ok"] is False
    assert data["build"]["problems"][0]["fix"] == "compose clarity"

    text = cli("clarity", "status")
    assert text.exit_code == 0, text.output
    assert "Verdict: FAIL, current" in text.output and "Questions: 1 pending" in text.output


def test_validate_exits_1_on_fail(cli: Callable[..., Result], fake: FakeEngine, repo: Path) -> None:
    assert cli("clarity", "--mode", "auto").exit_code == 0
    result = cli("clarity", "validate")
    assert result.exit_code == 1, result.output
    assert "CLARITY: FAIL" in result.output
    assert called(fake)[-1] == "clarity-validate"


def test_merge_is_pending_without_a_pass(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path
) -> None:
    assert cli("clarity", "merge").exit_code == 1  # no clarity branch yet
    assert cli("clarity", "--mode", "auto").exit_code == 0
    result = cli("clarity", "merge", "--json")
    assert result.exit_code == 1
    assert as_json(result) == {"merged": False, "pending_reason": "no PASS verdict is recorded"}
