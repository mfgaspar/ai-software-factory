"""Repo-scoped runs (``scope: repo``): no feature, the clarity worktree, a repo lock."""

from __future__ import annotations

import pytest

from compose.clarity import preflight
from compose.core import locks, store
from compose.core.models import Feature, Run, RunStatus
from compose.repos import git
from compose.runner.errors import RunError
from compose.runner.recovery import recover_stale_runs
from compose.tracking import views
from compose.workflows.loader import WorkflowError
from tests.unit.runner_helpers import Env

PROBE = (
    'printf "%s|%s|%s" "$COMPOSE_SCOPE" "${COMPOSE_FEATURE-unset}"'
    ' "{{ context.repo.dir }}" > probe.txt'
)

REPO_WORKFLOW = f"""
workflow: {{id: tidy, name: Tidy, scope: repo}}
steps:
  - id: probe
    run: '{PROBE}'
"""

PAUSING_WORKFLOW = """
workflow: {id: ask, name: Ask, scope: repo}
steps:
  - {id: wait, type: gate, message: "answer me"}
"""

FEATURE_WORKFLOW = """
workflow: {id: f, name: F}
steps:
  - {id: s, run: "true"}
"""


async def test_repo_run_has_no_feature_and_works_in_clarity_worktree(env: Env) -> None:
    branches = git.local_branches(env.repo_path)
    run = await env.runner().start(env.repo, env.workflow(REPO_WORKFLOW))
    assert run.status is RunStatus.COMPLETED, run.error
    assert run.feature_id is None
    assert store.select(env.db, Feature) == []
    assert set(git.local_branches(env.repo_path)) == {*branches, "clarity"}
    workdir = env.worktree(run)
    assert workdir == (env.home.worktrees / env.repo.name / "clarity").resolve()
    assert git.current_branch(workdir) == "clarity"
    assert (workdir / "probe.txt").read_text() == f"repo|unset|{workdir}"
    events = env.files(run).read_events()
    assert events[0] == {**events[0], "type": "run_created", "scope": "repo"}


async def test_feature_run_sets_scope_feature(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: feat, name: Feat}
        steps:
          - {id: probe, run: 'printf "%s|%s" "$COMPOSE_SCOPE" "$COMPOSE_FEATURE" > probe.txt'}
        """
    )
    run = await env.runner().start(env.repo, wf, feature="001-thing")
    assert run.status is RunStatus.COMPLETED, run.error
    assert (env.worktree(run) / "probe.txt").read_text() == "feature|001-thing"


async def test_second_repo_run_refused_while_one_is_paused(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = env.runner()
    paused = await runner.start(env.repo, env.workflow(PAUSING_WORKFLOW))
    assert paused.status is RunStatus.PAUSED
    with pytest.raises(RunError, match=f"active clarity run \\({paused.id}\\)"):
        runner.create_run(env.repo, env.workflow(REPO_WORKFLOW, name="tidy"))
    # feature runs aren't affected (past the pre-run check: clarity has started here)
    monkeypatch.setattr(preflight, "check", lambda *a, **k: preflight.Preflight())
    feature_wf = env.workflow(FEATURE_WORKFLOW, name="f")
    assert runner.create_run(env.repo, feature_wf).feature_id is not None
    runner.request_abort(paused.id)
    again = runner.create_run(env.repo, env.workflow(REPO_WORKFLOW, name="tidy"))
    assert again.feature_id is None


async def test_repo_run_refused_while_repo_lock_is_live(env: Env) -> None:
    lock = locks.acquire(env.db, locks.repo_lock_key(env.repo.id), run_id="run_other")
    try:
        with pytest.raises(RunError, match="run_other"):
            env.runner().create_run(env.repo, env.workflow(REPO_WORKFLOW))
    finally:
        lock.release()


def test_repo_scoped_workflow_cannot_use_context_feature(env: Env) -> None:
    with pytest.raises(WorkflowError, match="has no feature"):
        env.workflow(
            """
            workflow: {id: bad, name: Bad, scope: repo}
            steps:
              - {id: s, run: "echo {{ context.feature.dir }}"}
            """
        )


def _mark_running(env: Env, run: Run) -> None:
    run.status = RunStatus.RUNNING
    store.update(env.db, run)


def test_recovery_keeps_live_repo_run_and_fails_dead_one(env: Env) -> None:
    run = env.runner().create_run(env.repo, env.workflow(REPO_WORKFLOW))
    _mark_running(env, run)
    lock = locks.acquire(env.db, locks.repo_lock_key(env.repo.id), run_id=run.id)
    try:
        assert recover_stale_runs(env.db, env.home) == []
    finally:
        lock.release()
    assert [r.id for r in recover_stale_runs(env.db, env.home)] == [run.id]
    assert store.get(env.db, Run, run.id).status is RunStatus.FAILED  # type: ignore[union-attr]


async def test_run_detail_shows_workdir(env: Env) -> None:
    run = await env.runner().start(env.repo, env.workflow(REPO_WORKFLOW))
    detail = views.run_detail(env.db, env.home, run.id)
    assert detail["feature"] is None
    assert detail["worktree"] == str(env.worktree(run))


async def test_cli_text_says_clarity(env: Env, cli) -> None:  # type: ignore[no-untyped-def]
    run = await env.runner().start(env.repo, env.workflow(REPO_WORKFLOW))
    shown = cli("status", run.id)
    assert shown.exit_code == 0, shown.output
    assert "scope repo" in shown.output
    assert "feature None" not in shown.output
