from __future__ import annotations

import pytest

from compose.core import store
from compose.core.db import Database, IntegrityError
from compose.core.ids import new_id
from compose.core.models import (
    ExecStatus,
    Feature,
    HookExec,
    HookKind,
    Repo,
    Run,
    RunStatus,
    StepExec,
)


@pytest.fixture
def graph(db: Database) -> dict[str, str]:
    repo = store.insert(db, Repo(id=new_id("repo"), name="demo", path="/tmp/demo"))
    feature = store.insert(
        db,
        Feature(
            id=new_id("feat"),
            repo_id=repo.id,
            number=3,
            slug="user-auth",
            name="003-user-auth",
            branch="003-user-auth",
        ),
    )
    run = store.insert(
        db,
        Run(
            id=new_id("run"),
            repo_id=repo.id,
            feature_id=feature.id,
            workflow_id="quick",
            workflow_version="1.0.0",
            inputs={"spec": "add login", "n": 2, "flag": True},
        ),
    )
    step = store.insert(
        db, StepExec(id=new_id("exec"), run_id=run.id, step_id="plan", step_type="command")
    )
    return {"repo": repo.id, "feature": feature.id, "run": run.id, "step": step.id}


def test_repo_round_trip(db: Database) -> None:
    repo = Repo(id="repo_1", name="r", path="/r", origin_url="git@x:y.git", default_branch="main")
    store.insert(db, repo)
    assert store.get(db, Repo, "repo_1") == repo


def test_run_round_trip_with_json(db: Database, graph: dict[str, str]) -> None:
    run = store.get(db, Run, graph["run"])
    assert run is not None
    assert run.inputs == {"spec": "add login", "n": 2, "flag": True}
    assert run.status is RunStatus.CREATED
    assert run.outputs is None
    assert run.abort_requested is False

    run.status = RunStatus.PAUSED
    run.outputs = {"plan_path": "specs/003/plan.md"}
    run.abort_requested = True
    store.update(db, run)
    assert store.get(db, Run, run.id) == run


def test_step_exec_metrics_round_trip(db: Database, graph: dict[str, str]) -> None:
    step = store.get(db, StepExec, graph["step"])
    assert step is not None
    step.status = ExecStatus.COMPLETED
    step.cost_usd = 0.4213
    step.input_tokens = 1200
    step.cache_read_tokens = 50
    step.lines_added = 10
    step.output = {"exit_code": 0, "data": [1, 2]}
    store.update(db, step)
    assert store.get(db, StepExec, step.id) == step


def test_hook_exec_round_trip(db: Database, graph: dict[str, str]) -> None:
    hook = HookExec(
        id=new_id("hook"),
        run_id=graph["run"],
        step_exec_id=graph["step"],
        event="after_plan",
        hook_index=0,
        kind=HookKind.RUN,
        name="npm test",
        optional=True,
        cost_usd=0.0,
    )
    store.insert(db, hook)
    assert store.get(db, HookExec, hook.id) == hook


def test_select(db: Database, graph: dict[str, str]) -> None:
    for i in range(3):
        store.insert(
            db,
            StepExec(
                id=new_id("exec"),
                run_id=graph["run"],
                step_id="loop",
                step_type="command",
                iteration=i,
            ),
        )
    loops = store.select(
        db, StepExec, "run_id = ? AND step_id = ?", (graph["run"], "loop"), "iteration"
    )
    assert [s.iteration for s in loops] == [0, 1, 2]


def test_update_missing_raises(db: Database) -> None:
    with pytest.raises(LookupError):
        store.update(db, Repo(id="nope", name="n", path="/n"))


def test_status_check_constraint(db: Database, graph: dict[str, str]) -> None:
    with pytest.raises(IntegrityError):
        db.execute("UPDATE runs SET status = 'bogus' WHERE id = ?", (graph["run"],))


def test_foreign_keys_enforced(db: Database) -> None:
    with pytest.raises(IntegrityError):
        store.insert(db, Run(id="run_x", repo_id="missing", workflow_id="w", workflow_version="1"))


def test_cascade_delete(db: Database, graph: dict[str, str]) -> None:
    with db.transaction() as conn:
        conn.execute("DELETE FROM repos WHERE id = ?", (graph["repo"],))
    assert store.get(db, StepExec, graph["step"]) is None
