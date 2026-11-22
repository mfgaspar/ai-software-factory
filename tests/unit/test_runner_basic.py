from __future__ import annotations

from pathlib import Path

import pytest

from compose.core import store
from compose.core.models import ExecStatus, Feature, RunStatus
from compose.engines.base import Usage
from compose.engines.fake import Act, Script, edit
from compose.runner.errors import InputError, RunError
from compose.runner.state import (
    ALLOWED_TRANSITIONS,
    RunState,
    TransitionError,
    atomic_write,
    check_transition,
)
from tests.unit.runner_helpers import Env, interaction

LINEAR = """
workflow: {id: linear, name: Linear}
inputs:
  spec: {type: string, required: true}
outputs:
  said: {value: "{{ steps.plan.output.text }}"}
steps:
  - id: specify
    command: compose-specify
    input: {args: "{{ inputs.spec }}"}
  - id: plan
    prompt: "Plan {{ context.feature.name }}"
  - id: check
    run: 'echo "$COMPOSE_FEATURE $COMPOSE_RUN_ID" && cat specs/notes.md'
"""


async def test_linear_run(env: Env) -> None:
    env.fake.scripts = {
        "compose-specify": Script(
            [Act(say="writing spec"), *edit("specs/notes.md", "hello\n", cost=0.25)],
            final_text="spec done",
        )
    }
    env.fake.default = Script(
        [Act(usage=Usage(10, 5, cost_usd=0.1, turns=1))], final_text="planned"
    )
    run = await env.runner().start(env.repo, env.workflow(LINEAR), {"spec": "Add photo albums"})

    assert run.status is RunStatus.COMPLETED, run.error
    assert run.outputs == {"said": "planned"}
    feature = store.get(env.db, Feature, run.feature_id)
    assert feature is not None and feature.name == "001-add-photo-albums"

    execs = env.execs(run)
    assert [e.step_id for e in execs] == ["specify", "plan", "check"]
    assert all(e.status is ExecStatus.COMPLETED for e in execs)
    specify = execs[0]
    assert (specify.engine, specify.model, specify.session_id) == (
        "fake",
        "default-model",
        "fake-session",
    )
    assert specify.cost_usd == 0.25 and specify.input_tokens == 100
    check = execs[2].output
    assert check is not None and check["exit_code"] == 0
    assert check["stdout"].startswith(f"001-add-photo-albums {run.id}")
    assert "hello" in check["stdout"]

    task, cwd, options = env.fake.calls[0]
    assert task.label == "/compose-specify Add photo albums"
    assert cwd == env.worktree(run)
    assert options.env["COMPOSE_FEATURE"] == "001-add-photo-albums"
    assert env.fake.calls[1][0].text == "Plan 001-add-photo-albums"

    kinds = [(a.kind, a.tool_name) for a in env.actions(run)]
    assert kinds[:3] == [("message", None), ("tool_call", "Write"), ("tool_result", None)]
    assert ("tool_call", "shell") in kinds

    files = env.files(run)
    assert files.read_state().status == "completed"
    types = [e["type"] for e in files.read_events()]
    assert types[0] == "run_created" and types[-1] == "run_finished"
    assert "engine_event" in types
    assert (files.steps_dir / f"{specify.id}.json").exists()
    assert [e["type"] for e in env.events][0] == "run_started"
    # The user's checkout is untouched; work happened in the feature worktree.
    assert not (env.repo_path / "specs").exists()


async def test_failure_stops_run(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: fails, name: Fails}
        steps:
          - {id: bad, run: "echo oops >&2; exit 3"}
          - {id: never, run: "echo never"}
        """
    )
    run = await env.runner().start(env.repo, wf)
    assert run.status is RunStatus.FAILED
    assert "step 'bad' failed: exit code 3" in (run.error or "")
    bad = env.exec_of(run, "bad")[0]
    assert bad.status is ExecStatus.FAILED and bad.output is not None
    assert bad.output["stderr"].strip() == "oops"
    assert env.exec_of(run, "never") == []


async def test_continue_on_error_and_branch_on_exit_code(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: coe, name: COE}
        steps:
          - {id: test, run: "exit 1", continue_on_error: true}
          - id: branch
            type: if
            condition: "{{ steps.test.output.exit_code != 0 and steps.test.status == 'failed' }}"
            then: [{id: fix, run: "echo fixing"}]
            else: [{id: fine, run: "echo fine"}]
        """
    )
    run = await env.runner().start(env.repo, wf)
    assert run.status is RunStatus.COMPLETED
    assert env.exec_of(run, "fix") and not env.exec_of(run, "fine")
    branch = env.exec_of(run, "branch")[0]
    assert branch.output == {"branch": "then"}
    assert env.exec_of(run, "fix")[0].parent_exec_id == branch.id


async def test_switch(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: sw, name: SW}
        inputs: {size: {type: string, default: large}}
        steps:
          - id: pick
            type: switch
            expression: "{{ inputs.size }}"
            cases:
              small: [{id: s, run: "true"}]
              large: [{id: l, run: "true"}]
            default: [{id: d, run: "true"}]
        """
    )
    run = await env.runner().start(env.repo, wf)
    assert [e.step_id for e in env.execs(run)] == ["pick", "l"]
    run2 = await env.runner().start(env.repo, wf, {"size": "medium"})
    assert [e.step_id for e in env.execs(run2)] == ["pick", "d"]
    assert env.exec_of(run2, "pick")[0].output == {"case": "default", "value": "medium"}


async def test_engine_settings_precedence(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: models, name: M, model: wf-model, engine_options: {a: 1}}
        steps:
          - {id: one, prompt: "one"}
          - {id: two, prompt: "two", model: step-model, engine_options: {b: 2}}
        """
    )
    await env.runner().start(env.repo, wf)
    models = [c[2].model for c in env.fake.calls]
    assert models == ["wf-model", "step-model"]
    assert env.fake.calls[1][2].engine_options == {"a": 1, "b": 2}


async def test_unknown_engine_fails_step(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: eng, name: E}
        steps: [{id: one, prompt: "x", engine: nope}]
        """
    )
    run = await env.runner().start(env.repo, wf)
    assert run.status is RunStatus.FAILED
    assert "Engine 'nope' is not available" in (run.error or "")


async def test_engine_failure(env: Env) -> None:
    env.fake.default = Script(fail="model refused")
    wf = env.workflow("workflow: {id: e2, name: E}\nsteps: [{id: one, prompt: x}]\n")
    run = await env.runner().start(env.repo, wf)
    assert run.status is RunStatus.FAILED and "model refused" in (run.error or "")


async def test_expression_error_fails_step(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: ex, name: Ex}
        inputs: {n: {type: number, default: 1}}
        steps: [{id: one, run: "echo {{ inputs.n | join }}"}]
        """
    )
    run = await env.runner().start(env.repo, wf)
    assert run.status is RunStatus.FAILED
    assert "expression error" in (run.error or "")


async def test_shell_json_and_timeout(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: sh, name: Sh}
        steps:
          - {id: data, run: "echo '{\\"n\\": 2}'", output_format: json}
          - {id: use, run: "test {{ steps.data.output.data.n }} = 2"}
          - {id: slow, run: "sleep 5", timeout: 0.3}
        """
    )
    run = await env.runner().start(env.repo, wf)
    assert env.exec_of(run, "data")[0].output["data"] == {"n": 2}  # type: ignore[index]
    assert env.exec_of(run, "use")[0].status is ExecStatus.COMPLETED
    slow = env.exec_of(run, "slow")[0]
    assert slow.status is ExecStatus.FAILED and slow.error == "timeout after 0.3s"
    assert slow.duration_ms is not None and slow.duration_ms < 3000


async def test_strict_shell_passes_values_via_env(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: strict, name: S}
        inputs: {title: {type: string, default: "a; rm -rf / #"}}
        steps:
          - id: safe
            type: shell
            strict: true
            env: {TITLE: "{{ inputs.title }}"}
            run: 'printf "%s" "$TITLE"'
        """
    )
    run = await env.runner().start(env.repo, wf)
    assert env.exec_of(run, "safe")[0].output["stdout"] == "a; rm -rf / #"  # type: ignore[index]


async def test_inputs(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: inp, name: Inp}
        inputs:
          spec: {type: string, required: true}
          n: {type: number, default: 2}
          go: {type: boolean}
        steps: [{id: a, run: "true"}]
        """
    )
    runner = env.runner()
    with pytest.raises(InputError, match="Missing required input 'spec'"):
        runner.create_run(env.repo, wf, {})
    with pytest.raises(InputError, match="Unknown input"):
        runner.create_run(env.repo, wf, {"spec": "x", "bogus": 1})
    with pytest.raises(InputError, match="'n'"):
        runner.create_run(env.repo, wf, {"spec": "x", "n": "lots"})
    run = runner.create_run(env.repo, wf, {"spec": "x", "go": "yes"})
    assert run.inputs == {"spec": "x", "n": 2, "go": True}
    assert run.status is RunStatus.CREATED

    asked = env.runner(interaction=interaction(ask_input=lambda name, spec: "from prompt"))
    run2 = asked.create_run(env.repo, wf, {})
    assert run2.inputs["spec"] == "from prompt"


async def test_feature_naming_and_reuse(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: names, name: Names}
        inputs:
          spec: {type: string, required: true}
          feature_name: {type: string}
        steps: [{id: a, run: "true"}]
        """
    )
    runner = env.runner()
    first = await runner.start(env.repo, wf, {"spec": "Build search", "feature_name": "Find"})
    second = await runner.start(env.repo, wf, {"spec": "Something else"})
    names = [
        store.get(env.db, Feature, r.feature_id).name  # type: ignore[union-attr]
        for r in (first, second)
    ]
    assert names == ["001-find", "002-something-else"]
    again = await runner.start(env.repo, wf, {"spec": "more"}, feature="001-find")
    assert again.feature_id == first.feature_id
    assert env.worktree(again) == env.worktree(first)
    with pytest.raises(RunError, match="not a feature name"):
        runner.create_run(env.repo, wf, {"spec": "x"}, feature="bad")


async def test_busy_feature_rejected(env: Env) -> None:
    from compose.core import locks

    wf = env.workflow("workflow: {id: b, name: B}\nsteps: [{id: a, run: 'true'}]\n")
    runner = env.runner()
    run = runner.create_run(env.repo, wf, feature="001-busy")
    with locks.acquire(env.db, locks.feature_lock_key(run.feature_id or ""), run_id="run_other"):
        with pytest.raises(RunError, match="already has an active run"):
            runner.create_run(env.repo, wf, feature="001-busy")
        with pytest.raises(RunError, match="already has an active run"):
            await runner.execute(run.id)


def test_transitions() -> None:
    check_transition(RunStatus.CREATED, RunStatus.RUNNING)
    check_transition(RunStatus.PAUSED, RunStatus.RUNNING)
    check_transition(RunStatus.FAILED, RunStatus.RUNNING)
    for status in (RunStatus.COMPLETED, RunStatus.ABORTED):
        assert ALLOWED_TRANSITIONS[status] == frozenset()
        with pytest.raises(TransitionError):
            check_transition(status, RunStatus.RUNNING)
    with pytest.raises(TransitionError):
        check_transition(RunStatus.PAUSED, RunStatus.COMPLETED)


def test_state_round_trip_and_atomic_write(tmp_path: Path) -> None:
    state = RunState(status="paused", attempts={"a": 2}, gate_choices={"g": "approve"})
    target = tmp_path / "s" / "state.json"
    import json

    atomic_write(target, json.dumps(state.to_json()))
    assert RunState.from_json(json.loads(target.read_text())) == state
    assert [p.name for p in target.parent.iterdir()] == ["state.json"]
