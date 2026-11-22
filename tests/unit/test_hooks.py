from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from compose.core import store
from compose.core.models import ExecStatus, HookExec, HookKind, Run, RunStatus
from compose.engines.base import EngineOptions, EngineTask, Usage
from compose.engines.fake import Act, Script
from compose.runner import hooks
from compose.workflows import loader
from tests.unit.runner_helpers import Env, interaction


def parse(body: str) -> loader.Workflow:
    return loader.parse_workflow(textwrap.dedent(body), "wf.yml")


def hook_rows(env: Env, run: Run) -> list[HookExec]:
    return store.select(env.db, HookExec, "run_id = ?", (run.id,), "started_at, id")


def user_hooks(env: Env, run: Run) -> list[HookExec]:
    return [h for h in hook_rows(env, run) if h.kind is not HookKind.BUILTIN]


def log_lines(env: Env, run: Run) -> list[str]:
    path = env.worktree(run) / "hooks.log"
    return path.read_text().split() if path.exists() else []


def log(word: str) -> str:
    return f"echo {word} >> hooks.log"


# ----------------------------------------------------------------- resolution


ORDERED = """
workflow: {id: ordered, name: Ordered}
hooks:
  before_step: {run: "true", description: any-before}
  before_build:
    - {run: "true", description: late, priority: 20}
    - {run: "true", description: first-declared}
    - {run: "true", description: early, priority: 1}
    - {run: "true", description: second-declared}
  after_build: {run: "true", description: build-after}
  after_step: {run: "true", description: any-after}
  before_run: {run: "true", description: run-before}
steps:
  - {id: build, run: "true"}
  - {id: other, run: "true"}
"""


def test_step_hooks_order_and_tracking() -> None:
    plan = hooks.step_hooks(parse(ORDERED), "build")
    assert [h.name for h in plan.before] == [
        "compose.track.begin",
        "any-before",
        "early",
        "first-declared",
        "second-declared",
        "late",
    ]
    assert [h.name for h in plan.after] == ["build-after", "any-after"]
    assert [h.name for h in plan.final] == ["compose.track.end"]
    other = hooks.step_hooks(parse(ORDERED), "other")
    assert [h.name for h in other.before] == ["compose.track.begin", "any-before"]
    assert [h.name for h in other.after] == ["any-after"]


def test_tracking_off_and_builtins_only() -> None:
    untracked = parse(ORDERED.replace("name: Ordered}", "name: Ordered, tracking: false}"))
    plan = hooks.step_hooks(untracked, "other")
    assert [h.name for h in plan.before] == ["any-before"]
    assert plan.final == []
    only = hooks.step_hooks(parse(ORDERED), "build", workflow_hooks=False)
    assert [h.name for h in only.before] == ["compose.track.begin"]
    assert only.after == []
    assert not hooks.step_hooks(untracked, "build", workflow_hooks=False)


def test_run_hooks() -> None:
    assert [h.name for h in hooks.run_hooks(parse(ORDERED), "before")] == ["run-before"]
    assert hooks.run_hooks(parse(ORDERED), "after") == []


def test_hooks_on_control_steps_are_rejected() -> None:
    with pytest.raises(loader.WorkflowError, match="'choose' is a step of type 'if'; hooks"):
        parse(
            """
            workflow: {id: bad, name: Bad}
            hooks:
              before_choose: {run: "true"}
            steps:
              - id: choose
                type: if
                condition: "{{ true }}"
                then: [{id: inner, run: "true"}]
            """
        )


# ------------------------------------------------------------------ execution


AROUND = f"""
workflow: {{id: around, name: Around}}
hooks:
  before_run: {{run: "{log("before_run")}"}}
  after_run: {{run: "{log("after_run")}"}}
  before_step: {{run: "{log("before_step")}"}}
  after_step: {{run: "{log("after_step")}"}}
  before_build: {{run: "{log("before_build")}"}}
  after_build: {{run: "{log("after_build")}"}}
steps:
  - {{id: build, run: "{log("build")}"}}
  - {{id: test, run: "{log("test")}"}}
"""


async def test_hooks_run_in_order(env: Env) -> None:
    run = await env.runner().start(env.repo, env.workflow(AROUND))
    assert run.status is RunStatus.COMPLETED, run.error
    assert log_lines(env, run) == [
        "before_run",
        "before_step",
        "before_build",
        "build",
        "after_build",
        "after_step",
        "before_step",
        "test",
        "after_step",
        "after_run",
    ]
    rows = hook_rows(env, run)
    assert all(r.status is ExecStatus.COMPLETED for r in rows)
    build = env.exec_of(run, "build")[0]
    names = [(r.event, r.name) for r in rows if r.step_exec_id == build.id]
    assert names == [
        ("before_step", "compose.track.begin"),
        ("before_step", log("before_step")),
        ("before_build", log("before_build")),
        ("after_build", log("after_build")),
        ("after_step", log("after_step")),
        ("after_step", "compose.track.end"),
    ]
    run_level = [r.event for r in rows if r.step_exec_id is None]
    assert run_level == ["before_run", "after_run"]
    types = [e["type"] for e in env.events]
    assert "hook_started" in types and "hook_finished" in types
    shell_calls = [a for a in env.actions(run) if a.tool_name == "shell" and a.hook_exec_id]
    assert len(shell_calls) == 2 * 8  # call + result for every user hook


def failing(event: str, *, optional: bool = False) -> str:
    return f"""
workflow: {{id: failing, name: Failing}}
hooks:
  {event}:
    - {{run: "exit 3", description: broken, optional: {str(optional).lower()}}}
    - {{run: "{log(event)}"}}
steps:
  - id: work
    prompt: do the work
  - {{id: next, run: "{log("next")}"}}
"""


async def test_required_before_hook_failure_skips_the_step(env: Env) -> None:
    run = await env.runner().start(env.repo, env.workflow(failing("before_work")))
    assert run.status is RunStatus.FAILED
    assert run.error == ("step 'work' failed: before_work hook 'broken' failed: exit code 3")
    assert env.fake.calls == []  # the step never ran
    work = env.exec_of(run, "work")[0]
    assert work.status is ExecStatus.FAILED
    assert log_lines(env, run) == []  # later hooks in the group don't run either
    statuses = {r.name: r.status for r in hook_rows(env, run)}
    assert statuses["broken"] is ExecStatus.FAILED
    assert statuses["compose.track.end"] is ExecStatus.COMPLETED  # tracking still closes


async def test_optional_before_hook_failure_is_recorded_only(env: Env) -> None:
    run = await env.runner().start(env.repo, env.workflow(failing("before_work", optional=True)))
    assert run.status is RunStatus.COMPLETED, run.error
    assert len(env.fake.calls) == 1
    assert log_lines(env, run) == ["before_work", "next"]
    broken = next(r for r in hook_rows(env, run) if r.name == "broken")
    assert broken.status is ExecStatus.FAILED and broken.optional
    assert broken.error == "exit code 3"


async def test_required_after_hook_failure_fails_the_step(env: Env) -> None:
    run = await env.runner().start(env.repo, env.workflow(failing("after_work")))
    assert run.status is RunStatus.FAILED
    assert run.error == "step 'work' failed: after_work hook 'broken' failed: exit code 3"
    assert len(env.fake.calls) == 1
    work = env.exec_of(run, "work")[0]
    assert work.status is ExecStatus.FAILED
    assert work.output is not None and work.output["text"] == "done"  # step output kept
    assert env.exec_of(run, "next") == []


async def test_optional_after_hook_failure_is_recorded_only(env: Env) -> None:
    run = await env.runner().start(env.repo, env.workflow(failing("after_work", optional=True)))
    assert run.status is RunStatus.COMPLETED, run.error
    assert log_lines(env, run) == ["after_work", "next"]


async def test_after_hooks_skip_failed_steps(env: Env) -> None:
    wf = f"""
workflow: {{id: skipafter, name: SkipAfter}}
hooks:
  after_step: {{run: "{log("after_step")}"}}
steps:
  - {{id: bad, run: "exit 1", continue_on_error: true}}
  - {{id: good, run: "{log("good")}"}}
"""
    run = await env.runner().start(env.repo, env.workflow(wf))
    assert run.status is RunStatus.COMPLETED, run.error
    assert log_lines(env, run) == ["good", "after_step"]
    bad = env.exec_of(run, "bad")[0]
    names = [r.name for r in hook_rows(env, run) if r.step_exec_id == bad.id]
    assert names == ["compose.track.begin", "compose.track.end"]


async def test_conditions_and_rendering(env: Env) -> None:
    wf = """
workflow: {id: cond, name: Cond}
inputs:
  notify: {type: boolean, default: false}
  who: {type: string, default: team}
hooks:
  after_work:
    - run: 'echo "$TARGET {{ steps.work.output.exit_code }}" >> hooks.log'
      env: {TARGET: "{{ inputs.who }}"}
    - run: echo notified >> hooks.log
      description: notify
      condition: "{{ inputs.notify }}"
steps:
  - {id: work, run: "true"}
"""
    run = await env.runner().start(env.repo, env.workflow(wf))
    assert log_lines(env, run) == ["team", "0"]
    notify = next(r for r in hook_rows(env, run) if r.name == "notify")
    assert notify.status is ExecStatus.SKIPPED and notify.error == "condition is false"

    run2 = await env.runner().start(
        env.repo, env.workflow(wf), {"notify": True, "who": "ops"}, feature="002-other"
    )
    assert log_lines(env, run2)[-3:] == ["ops", "0", "notified"]


ASKING = f"""
workflow: {{id: asking, name: Asking}}
hooks:
  after_work:
    run: "{log("checklist")}"
    optional: true
    prompt_text: "Generate a checklist for {{{{ context.feature.name }}}}?"
steps:
  - {{id: work, run: "true"}}
"""


@pytest.mark.parametrize(
    ("answer", "expected", "status"),
    [(True, ["checklist"], ExecStatus.COMPLETED), (False, [], ExecStatus.SKIPPED)],
)
async def test_prompt_text_asks_on_a_terminal(
    env: Env, answer: bool, expected: list[str], status: ExecStatus
) -> None:
    questions: list[str] = []

    def confirm(question: str) -> bool:
        questions.append(question)
        return answer

    runner = env.runner(interaction=interaction(ask_confirm=confirm))
    run = await runner.start(env.repo, env.workflow(ASKING), feature="001-ask")
    assert run.status is RunStatus.COMPLETED, run.error
    assert questions == ["Generate a checklist for 001-ask?"]
    assert log_lines(env, run) == expected
    assert user_hooks(env, run)[0].status is status


async def test_prompt_text_runs_without_a_terminal(env: Env) -> None:
    run = await env.runner().start(env.repo, env.workflow(ASKING))
    assert log_lines(env, run) == ["checklist"]


async def test_engine_hooks_roll_into_the_step(env: Env) -> None:
    def script(task: EngineTask, cwd: Path, options: EngineOptions) -> Script:
        if task.kind == "skill":
            cost = 0.5
        elif task.text == "review it":
            cost = 0.25
        else:
            cost = 1.0
        return Script(
            [Act(say=task.label), Act(usage=Usage(10, 5, cost_usd=cost, turns=1))],
            final_text=task.label,
        )

    env.fake.scripts = script
    wf = """
workflow: {id: engine, name: Engine, model: wf-model}
hooks:
  before_work:
    command: compose-checklist
    args: "for {{ context.feature.name }}"
    model: hook-model
    env: {EXTRA: "yes"}
  after_work:
    prompt: review it
outputs:
  cost: {value: "{{ steps.work.cost_usd }}"}
steps:
  - id: work
    prompt: build it
"""
    run = await env.runner().start(env.repo, env.workflow(wf), feature="001-eng")
    assert run.status is RunStatus.COMPLETED, run.error
    work = env.exec_of(run, "work")[0]
    assert work.cost_usd == pytest.approx(1.75)
    assert work.input_tokens == 30 and work.output_tokens == 15
    assert work.turns == 1  # the step's own
    assert run.outputs == {"cost": pytest.approx(1.75)}

    before, after = user_hooks(env, run)
    assert (before.kind, before.model, before.cost_usd) == (HookKind.COMMAND, "hook-model", 0.5)
    assert (after.kind, after.model, after.cost_usd) == (HookKind.PROMPT, "wf-model", 0.25)
    labels = [call[0].label for call in env.fake.calls]
    assert labels == ["/compose-checklist for 001-eng", "build it", "review it"]
    assert env.fake.calls[0][2].env["EXTRA"] == "yes"
    assert env.fake.calls[0][2].env["COMPOSE_FEATURE"] == "001-eng"

    messages = [a for a in env.actions(run) if a.kind == "message"]
    assert [(m.step_exec_id, m.hook_exec_id) for m in messages] == [
        (work.id, before.id),
        (work.id, None),
        (work.id, after.id),
    ]


async def test_hook_costs_count_toward_run_limit(env: Env) -> None:
    env.fake.default = Script([Act(usage=Usage(1, 1, cost_usd=0.6, turns=1))])
    wf = """
workflow: {id: capped, name: Capped, limits: {max_cost_usd: 1.0}}
hooks:
  before_work: {prompt: warm up}
steps:
  - id: work
    prompt: build it
"""
    run = await env.runner().start(env.repo, env.workflow(wf))
    assert run.status is RunStatus.FAILED
    assert "run cost $1.2000 exceeds max_cost_usd $1.0" in (run.error or "")


async def test_run_hooks_failure_and_resume(env: Env) -> None:
    marker = env.tmp / "allow"
    wf = f"""
workflow: {{id: runhooks, name: RunHooks}}
hooks:
  before_run: {{run: "{log("before_run")}"}}
  after_run:
    - {{run: "{log("after_run")}"}}
    - {{run: "test -f {marker}", description: gate-file}}
steps:
  - {{id: work, run: "{log("work")}"}}
"""
    runner = env.runner()
    run = await runner.start(env.repo, env.workflow(wf))
    assert run.status is RunStatus.FAILED
    assert run.error == "after_run hook 'gate-file' failed: exit code 1"

    marker.touch()
    run = await runner.resume(run.id)
    assert run.status is RunStatus.COMPLETED, run.error
    # before_run, the step and the first after_run hook are not repeated
    assert log_lines(env, run) == ["before_run", "work", "after_run"]


async def test_required_before_run_failure_runs_no_steps(env: Env) -> None:
    wf = f"""
workflow: {{id: norun, name: NoRun}}
hooks:
  before_run: {{run: "exit 2", description: preflight}}
  after_run: {{run: "{log("after_run")}"}}
steps:
  - {{id: work, run: "{log("work")}"}}
"""
    run = await env.runner().start(env.repo, env.workflow(wf))
    assert run.status is RunStatus.FAILED
    assert run.error == "before_run hook 'preflight' failed: exit code 2"
    assert env.execs(run) == []
    assert log_lines(env, run) == []


async def test_gate_hooks_do_not_repeat_on_resume(env: Env) -> None:
    wf = f"""
workflow: {{id: gated, name: Gated}}
hooks:
  before_review: {{run: "{log("before_review")}"}}
  after_review: {{run: "{log("after_review")}"}}
steps:
  - id: review
    type: gate
    message: OK?
"""
    runner = env.runner()
    run = await runner.start(env.repo, env.workflow(wf))
    assert run.status is RunStatus.PAUSED
    run = await runner.resume(run.id, choice="approve")
    assert run.status is RunStatus.COMPLETED, run.error
    assert log_lines(env, run) == ["before_review", "after_review"]
    names = [r.name for r in hook_rows(env, run)]
    assert names.count("compose.track.begin") == 1
    assert names.count("compose.track.end") == 1


async def test_fan_out_hooks_run_per_item(env: Env) -> None:
    wf = f"""
workflow: {{id: fan, name: Fan}}
hooks:
  before_each: {{run: 'echo "item-{{{{ item }}}}" >> hooks.log'}}
steps:
  - id: spread
    type: fan-out
    items: "{{{{ ['a', 'b'] }}}}"
    max_concurrency: 1
    step: {{id: each, run: "{log("ran")}"}}
"""
    run = await env.runner().start(env.repo, env.workflow(wf))
    assert run.status is RunStatus.COMPLETED, run.error
    assert log_lines(env, run) == ["item-a", "ran", "item-b", "ran"]
    spread = env.exec_of(run, "spread")[0]
    names = [r.name for r in hook_rows(env, run) if r.step_exec_id == spread.id]
    assert names == ["compose.track.begin", "compose.track.end"]


async def test_hook_timeout_fails_the_hook(env: Env) -> None:
    wf = """
workflow: {id: slow, name: Slow}
hooks:
  before_work: {run: "sleep 5", timeout: 0.2, description: slow}
steps:
  - {id: work, run: "true"}
"""
    run = await env.runner().start(env.repo, env.workflow(wf))
    assert run.status is RunStatus.FAILED
    assert run.error == "step 'work' failed: before_work hook 'slow' failed: timeout after 0.2s"


async def test_builtin_hooks_receive_the_step(env: Env) -> None:
    seen: list[tuple[str, str | None, str]] = []

    async def spy(call: hooks.BuiltinCall) -> None:
        step = call.step_exec.step_id if call.step_exec else None
        seen.append((call.hook_exec.name, step, call.hook_exec.event))

    original = dict(hooks.BUILTIN_IMPLS)
    try:
        hooks.register_builtin("compose.track.begin", spy)
        hooks.register_builtin("compose.track.end", spy)
        run = await env.runner().start(
            env.repo,
            env.workflow(
                """
                workflow: {id: spy, name: Spy}
                steps:
                  - {id: one, run: "true"}
                """
            ),
        )
    finally:
        hooks.BUILTIN_IMPLS.clear()
        hooks.BUILTIN_IMPLS.update(original)
    assert run.status is RunStatus.COMPLETED
    assert seen == [
        ("compose.track.begin", "one", "before_step"),
        ("compose.track.end", "one", "after_step"),
    ]
