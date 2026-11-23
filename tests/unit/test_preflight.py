"""The pre-run check for feature runs: one test per row of the design's table."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import Result

from compose.clarity import constitution, fingerprint, preflight, verdict
from compose.cli import runs
from compose.core.db import open_database
from compose.core.home import ensure_home
from compose.core.models import RunStatus
from compose.engines.fake import FakeEngine
from compose.engines.registry import EngineRegistry
from compose.repos import git
from compose.runner.errors import RunError
from tests.unit.runner_helpers import Env

FEATURE_WF = """
workflow: {id: feat, name: Feat}
inputs:
  spec: {type: string, required: true}
steps:
  - {id: build, run: echo built}
"""


def _commit(root: Path, files: dict[str, str], message: str = "clarity") -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    git.git(root, "add", "-A")
    git.git(root, "commit", "-q", "-m", message)


def _record(root: Path, result: str = "PASS", *, fp: str | None = None) -> str:
    """Commit verdict.yml for the committed ``.clarity/`` (or ``fp``); return its fingerprint."""
    fp = fp or fingerprint.of_ref(root, "HEAD")
    found = verdict.Verdict("PASS", 0) if result == "PASS" else verdict.Verdict("FAIL", 2)
    verdict.write(root, found, fp, "run-x")
    git.git(root, "add", "-A")
    git.git(root, "commit", "-q", "-m", "verdict")
    return fp


def _foundation(root: Path, *, result: str = "PASS", stale_constitution: bool = False) -> None:
    """A clarity foundation committed on the current branch, validated and stamped."""
    _commit(root, {".clarity/product/prd.md": "# PRD\n"})
    fp = fingerprint.of_ref(root, "HEAD")
    stamp = "stale" if stale_constitution else fp
    _commit(root, {constitution.CONSTITUTION_FILE: f"{constitution.marker(stamp)}\n# C\n"})
    _record(root, result, fp=fp)


def _refused(env: Env) -> preflight.PreflightError:
    with pytest.raises(preflight.PreflightError) as info:
        env.runner().create_run(env.repo, env.workflow(FEATURE_WF), {"spec": "a thing"})
    assert isinstance(info.value, RunError)
    assert env.db.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    assert env.db.conn.execute("SELECT COUNT(*) FROM features").fetchone()[0] == 0
    return info.value


def _fixes(error: preflight.PreflightError) -> list[str]:
    return [p.fix for p in error.problems]


def test_not_started_warns_and_starts(env: Env) -> None:
    runner = env.runner()
    run = runner.create_run(env.repo, env.workflow(FEATURE_WF), {"spec": "a thing"})
    assert run.status is RunStatus.CREATED
    assert runner.last_warnings == [preflight.NOT_STARTED]
    assert "No clarity foundation" in preflight.NOT_STARTED
    created = env.files(run).read_events()[0]
    assert created["type"] == "run_created" and created["warnings"] == [preflight.NOT_STARTED]


def test_started_on_the_clarity_branch_only_refuses(env: Env) -> None:
    git.create_branch(env.repo_path, "clarity", "main")
    error = _refused(env)
    assert _fixes(error) == ["compose clarity"]
    assert "in progress on branch `clarity`" in str(error)


def test_unmerged_pass_on_the_clarity_branch_suggests_merge(env: Env) -> None:
    root = env.repo_path
    git.git(root, "switch", "-q", "-c", "clarity")
    _foundation(root)
    git.git(root, "switch", "-q", "main")
    error = _refused(env)
    assert _fixes(error) == ["compose clarity merge"]


def test_missing_verdict_refuses(env: Env) -> None:
    root = env.repo_path
    _commit(root, {".clarity/product/prd.md": "# PRD\n"})
    fp = fingerprint.of_ref(root, "HEAD")
    _commit(root, {constitution.CONSTITUTION_FILE: f"{constitution.marker(fp)}\n# C\n"})
    error = _refused(env)
    assert _fixes(error) == ["compose clarity validate"]
    assert "doesn't pass" in str(error)


def test_fail_verdict_refuses(env: Env) -> None:
    _foundation(env.repo_path, result="FAIL")
    error = _refused(env)
    assert _fixes(error) == ["compose clarity validate"]
    assert "doesn't pass" in error.problems[0].message


def test_verdict_for_other_content_refuses(env: Env) -> None:
    root = env.repo_path
    _foundation(root)
    _commit(root, {".clarity/product/prd.md": "# PRD, edited since\n"})
    error = _refused(env)
    messages = [p.message for p in error.problems]
    assert any("changed since it was validated" in m for m in messages)
    assert any("constitution is out of date" in m for m in messages)


def test_stale_constitution_refuses(env: Env) -> None:
    _foundation(env.repo_path, stale_constitution=True)
    error = _refused(env)
    assert [p.message for p in error.problems] == ["The constitution is out of date with clarity."]
    assert _fixes(error) == ["compose clarity validate"]


def test_all_current_and_pass_starts_without_warnings(env: Env) -> None:
    _foundation(env.repo_path)
    runner = env.runner()
    run = runner.create_run(env.repo, env.workflow(FEATURE_WF), {"spec": "a thing"})
    assert run.status is RunStatus.CREATED
    assert runner.last_warnings == []
    assert preflight.check(env.repo).ok


def test_behind_upstream_says_pull_first(env: Env) -> None:
    root = env.repo_path
    git.git(root, "switch", "-q", "-c", "clarity")
    git.git(root, "switch", "-q", "main")
    _commit(root, {"later.txt": "x\n"}, "on the remote")
    git.git(root, "remote", "add", "origin", "https://example.invalid/repo.git")
    git.git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git.git(root, "branch", "--set-upstream-to=origin/main", "main")
    git.git(root, "reset", "-q", "--hard", "HEAD~1")
    error = _refused(env)
    assert "1 commit(s) behind origin/main: pull first" in str(error)


def test_no_upstream_no_hint(env: Env) -> None:
    git.create_branch(env.repo_path, "clarity", "main")
    assert "pull first" not in str(_refused(env))


def test_repo_scoped_runs_skip_the_check(env: Env) -> None:
    git.create_branch(env.repo_path, "clarity", "main")
    body = "workflow: {id: r, name: R, scope: repo}\nsteps:\n  - {id: a, run: echo}\n"
    run = env.runner().create_run(env.repo, env.workflow(body, name="r"))
    assert run.feature_id is None


def test_custom_clarity_branch_counts_as_started(env: Env) -> None:
    git.create_branch(env.repo_path, "foundation", "main")
    assert preflight.check(env.repo).warnings == [preflight.NOT_STARTED]
    found = preflight.check(env.repo, clarity_branch="foundation")
    assert [p.fix for p in found.problems] == ["compose clarity"]


# ---------------------------------------------------------------------- CLI


def test_compose_run_refuses_with_the_fix(
    cli: Callable[..., Result], git_repo: Path, monkeypatch: pytest.MonkeyPatch, compose_home: Path
) -> None:
    engine = FakeEngine()
    monkeypatch.setattr(runs, "engine_registry", lambda: EngineRegistry({"fake": engine}))
    (compose_home / "config.yml").write_text("defaults: {engine: fake}\n")
    assert cli("repo", "add", str(git_repo)).exit_code == 0
    monkeypatch.chdir(git_repo)
    (git_repo / "wf.yml").write_text(FEATURE_WF)
    git.create_branch(git_repo, "clarity", "main")

    result = cli("run", str(git_repo / "wf.yml"), "-i", "spec=a thing", "--no-interactive")
    assert result.exit_code == 1
    assert "hasn't passed yet" in result.output and "Fix: compose clarity" in result.output
    home = ensure_home()
    db = open_database(home)
    try:
        assert db.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    finally:
        db.close()
    assert engine.calls == []


def test_compose_run_warns_when_not_started(
    cli: Callable[..., Result], git_repo: Path, monkeypatch: pytest.MonkeyPatch, compose_home: Path
) -> None:
    monkeypatch.setattr(runs, "engine_registry", lambda: EngineRegistry({"fake": FakeEngine()}))
    (compose_home / "config.yml").write_text("defaults: {engine: fake}\n")
    assert cli("repo", "add", str(git_repo)).exit_code == 0
    monkeypatch.chdir(git_repo)
    (git_repo / "wf.yml").write_text(FEATURE_WF)
    result = cli("run", str(git_repo / "wf.yml"), "-i", "spec=a thing", "--no-interactive")
    assert result.exit_code == 0, result.output
    assert "warning: No clarity foundation" in result.output
