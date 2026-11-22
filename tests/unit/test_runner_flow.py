from __future__ import annotations

import asyncio

from compose.core.models import ExecStatus, RunStatus
from compose.engines.base import Usage
from compose.engines.fake import Act, Script, edit
from tests.unit.runner_helpers import Env, interaction


async def test_do_while_fix_until_green(env: Env) -> None:
    attempts = {"n": 0}

    def script(task, cwd, options):  # type: ignore[no-untyped-def]
        attempts["n"] += 1
        if attempts["n"] == 2:
            return Script(edit("fixed.txt", "ok\n", cost=0.1))
        return Script([Act(usage=Usage(cost_usd=0.1, turns=1))])

    env.fake.scripts = script
    wf = env.workflow(
        """
        workflow: {id: loop, name: Loop}
        steps:
          - id: fix-loop
            type: do-while
            max_iterations: 5
            condition: "{{ steps.test.output.exit_code != 0 }}"
            steps:
              - {id: fix, prompt: "fix it"}
              - {id: test, run: "test -f fixed.txt", continue_on_error: true}
        """
    )
    run = await env.runner().start(env.repo, wf)
    assert run.status is RunStatus.COMPLETED
    loop = env.exec_of(run, "fix-loop")[0]
    assert loop.output == {"iterations": 2, "exhausted": False}
    assert [e.iteration for e in env.exec_of(run, "test")] == [1, 2]
    assert loop.cost_usd == 0.2  # rolled up from the iterations


async def test_while_checks_first_and_exhausts(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: w, name: W}
        inputs: {go: {type: boolean, default: false}}
        steps:
          - id: never
            type: while
            max_iterations: 3
            condition: "{{ inputs.go }}"
            steps: [{id: a, run: "true"}]
          - id: always
            type: while
            max_iterations: 2
            condition: "true"
            steps: [{id: b, run: "true"}]
        """
    )
    run = await env.runner().start(env.repo, wf)
    assert env.exec_of(run, "never")[0].output == {"iterations": 0, "exhausted": False}
    assert env.exec_of(run, "always")[0].output == {"iterations": 2, "exhausted": True}
    assert env.exec_of(run, "a") == [] and len(env.exec_of(run, "b")) == 2


async def test_fan_out_and_fan_in(env: Env) -> None:
    env.fake.scripts = lambda task, cwd, options: Script(
        [Act(sleep=0.05), Act(usage=Usage(cost_usd=0.01, turns=1))], final_text=task.text.upper()
    )
    wf = env.workflow(
        """
        workflow: {id: fan, name: Fan}
        inputs: {services: {type: string, default: "api,web,db"}}
        steps:
          - id: per-service
            type: fan-out
            items: "{{ inputs.services | split(',') }}"
            max_concurrency: 2
            step: {id: review, prompt: "review {{ item }}"}
          - id: collect
            type: fan-in
            wait_for: [per-service]
            output:
              count: "{{ fan_in.results | length }}"
              texts: "{{ fan_in.results | map('text') | join('|') }}"
        """
    )
    run = await env.runner().start(env.repo, wf)
    assert run.status is RunStatus.COMPLETED, run.error
    fan = env.exec_of(run, "per-service")[0]
    assert fan.output is not None and fan.output["count"] == 3
    assert [r["text"] for r in fan.output["results"]] == ["REVIEW API", "REVIEW WEB", "REVIEW DB"]
    assert round(fan.cost_usd, 4) == 0.03
    assert env.exec_of(run, "collect")[0].output == {
        "count": 3,
        "texts": "REVIEW API|REVIEW WEB|REVIEW DB",
    }
    reviews = env.exec_of(run, "review")
    assert sorted(e.iteration or 0 for e in reviews) == [0, 1, 2]


async def test_gate_pause_and_resume_with_verdict_input(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: g, name: G}
        inputs: {verdict: {type: string, default: ""}}
        steps:
          - {id: before, run: "echo before"}
          - {id: review, type: gate, message: "Review it", verdict_input: verdict}
          - {id: after, run: "echo after"}
        """
    )
    runner = env.runner()
    run = await runner.start(env.repo, wf)
    assert run.status is RunStatus.PAUSED
    assert "waiting for a decision on gate 'review'" in (run.error or "")
    gate = env.exec_of(run, "review")[0]
    assert gate.status is ExecStatus.PAUSED

    resumed = await runner.resume(run.id, {"verdict": "approve"})
    assert resumed.status is RunStatus.COMPLETED
    gates = env.exec_of(run, "review")
    assert len(gates) == 1 and gates[0].output == {"choice": "approve"}  # same row reused
    assert len(env.exec_of(run, "before")) == 1  # not re-run
    assert len(env.exec_of(run, "after")) == 1


async def test_gate_choice_on_resume_and_reject_modes(env: Env) -> None:
    def wf_for(mode: str) -> object:
        return env.workflow(
            f"""
            workflow: {{id: g-{mode}, name: G}}
            steps:
              - {{id: review, type: gate, message: "ok?", on_reject: {mode}}}
              - {{id: after, run: "echo after"}}
            """,
            name=f"g-{mode}",
        )

    runner = env.runner()
    aborted = await runner.start(env.repo, wf_for("abort"), feature="001-a")  # type: ignore[arg-type]
    aborted = await runner.resume(aborted.id, choice="reject")
    assert aborted.status is RunStatus.ABORTED
    assert env.exec_of(aborted, "review")[0].output == {"choice": "reject"}
    assert env.exec_of(aborted, "after") == []

    skipped = await runner.start(env.repo, wf_for("skip"), feature="002-b")  # type: ignore[arg-type]
    skipped = await runner.resume(skipped.id, choice="reject")
    assert skipped.status is RunStatus.COMPLETED and env.exec_of(skipped, "after")

    retry = await runner.start(env.repo, wf_for("retry"), feature="003-c")  # type: ignore[arg-type]
    retry = await runner.resume(retry.id, choice="reject")
    assert retry.status is RunStatus.PAUSED and "rejected" in (retry.error or "")
    retry = await runner.resume(retry.id, choice="nonsense")
    assert retry.status is RunStatus.PAUSED and "invalid choice" in (retry.error or "")
    retry = await runner.resume(retry.id, choice="approve")
    assert retry.status is RunStatus.COMPLETED


async def test_gate_interactive(env: Env) -> None:
    answers = iter(["maybe", "approve"])
    runner = env.runner(interaction=interaction(ask_gate=lambda message, options: next(answers)))
    wf = env.workflow("workflow: {id: gi, name: G}\nsteps: [{id: r, type: gate, message: ok}]\n")
    run = await runner.start(env.repo, wf)
    assert run.status is RunStatus.COMPLETED
    assert env.exec_of(run, "r")[0].output == {"choice": "approve"}


async def test_nested_workflow_outputs_and_pause(env: Env) -> None:
    child_dir = env.repo_path / ".compose" / "workflows" / "child"
    child_dir.mkdir(parents=True)
    (child_dir / "workflow.yml").write_text(
        """
workflow: {id: child, name: Child}
inputs: {word: {type: string, required: true}}
outputs: {shout: {value: "{{ steps.say.output.stdout | upper }}"}}
steps:
  - {id: say, run: "printf {{ inputs.word }}"}
  - {id: ok, type: gate, message: "child gate"}
"""
    )
    wf = env.workflow(
        """
        workflow: {id: parent, name: Parent}
        steps:
          - id: call
            type: workflow
            workflow: child
            input: {word: hello}
          - {id: after, run: "echo {{ steps.call.output.shout }}"}
        """
    )
    runner = env.runner()
    run = await runner.start(env.repo, wf)
    assert run.status is RunStatus.PAUSED
    run = await runner.resume(run.id, choice="approve")
    assert run.status is RunStatus.COMPLETED, run.error
    after = env.exec_of(run, "after")[0].output
    assert after is not None and after["stdout"].strip() == "HELLO"
    call = env.exec_of(run, "call")[0]
    assert call.output is not None and call.output["shout"] == "HELLO"
    child_rows = env.db.conn.execute(
        "SELECT id, status, parent_exec_id FROM runs WHERE parent_run_id = ?", (run.id,)
    ).fetchall()
    assert [(r[1], r[2]) for r in child_rows] == [("completed", call.id)]


async def test_workflow_call_cycle(env: Env) -> None:
    folder = env.repo_path / ".compose" / "workflows"
    for name, target in (("ping", "pong"), ("pong", "ping")):
        (folder / name).mkdir(parents=True, exist_ok=True)
        (folder / name / "workflow.yml").write_text(
            f"workflow: {{id: {name}, name: {name}}}\n"
            f"steps: [{{id: call, type: workflow, workflow: {target}}}]\n"
        )
    from compose.workflows import loader

    run = await env.runner().start(env.repo, loader.resolve("ping", env.repo_path))
    assert run.status is RunStatus.FAILED
    assert "cycle: ping -> pong -> ping" in (run.error or "")


async def test_resume_after_failure_reruns_only_failed_step(env: Env) -> None:
    wf = env.workflow(
        """
        workflow: {id: rf, name: RF}
        steps:
          - {id: plan, prompt: "plan"}
          - {id: check, run: "test -f ready.txt"}
          - {id: done, run: "echo done"}
        """
    )
    runner = env.runner()
    run = await runner.start(env.repo, wf)
    assert run.status is RunStatus.FAILED
    (env.worktree(run) / "ready.txt").write_text("y")
    run = await runner.resume(run.id)
    assert run.status is RunStatus.COMPLETED
    assert len(env.fake.calls) == 1  # plan was not re-run
    checks = env.exec_of(run, "check")
    assert [(c.attempt, c.status) for c in checks] == [
        (1, ExecStatus.FAILED),
        (2, ExecStatus.COMPLETED),
    ]


async def test_abort_running_and_paused(env: Env) -> None:
    env.fake.default = Script([Act(say="thinking"), Act(sleep=10), Act(say="never")])
    wf = env.workflow("workflow: {id: ab, name: Ab}\nsteps: [{id: slow, prompt: x}]\n")
    runner = env.runner()
    run = runner.create_run(env.repo, wf)
    task = asyncio.create_task(runner.execute(run.id))
    for _ in range(500):
        await asyncio.sleep(0.02)
        if env.exec_of(run, "slow"):
            break
    assert env.exec_of(run, "slow"), "the step never started"
    runner.request_abort(run.id)
    finished = await asyncio.wait_for(task, timeout=5)
    assert finished.status is RunStatus.ABORTED
    assert env.exec_of(run, "slow")[0].status is ExecStatus.ABORTED

    gate = env.workflow("workflow: {id: ab2, name: A}\nsteps: [{id: r, type: gate, message: m}]\n")
    paused = await runner.start(env.repo, gate)
    assert runner.request_abort(paused.id).status is RunStatus.ABORTED


async def test_limits(env: Env) -> None:
    env.fake.default = Script([Act(usage=Usage(cost_usd=0.6, turns=1))] * 3)
    step_cap = env.workflow(
        """
        workflow: {id: lim, name: L}
        steps: [{id: big, prompt: x, limits: {max_cost_usd: 1.0}}]
        """
    )
    run = await env.runner().start(env.repo, step_cap)
    big = env.exec_of(run, "big")[0]
    assert big.status is ExecStatus.FAILED
    assert big.error is not None and big.error.startswith("limit_exceeded: step cost")
    assert big.cost_usd == 1.2  # recorded up to where it stopped

    env.fake.default = Script([Act(usage=Usage(cost_usd=0.4, turns=1))])
    run_cap = env.workflow(
        """
        workflow: {id: lim2, name: L, limits: {max_cost_usd: 1.0}}
        steps:
          - {id: a, prompt: x}
          - {id: b, prompt: x}
          - {id: c, prompt: x}
        """,
        name="lim2",
    )
    run2 = await env.runner().start(env.repo, run_cap)
    assert run2.status is RunStatus.FAILED
    assert "run cost" in (env.exec_of(run2, "c")[0].error or "")

    env.fake.default = Script([Act(usage=Usage(cost_usd=0, turns=1))] * 4)
    turns = env.workflow(
        "workflow: {id: t, name: T}\nsteps: [{id: a, prompt: x, limits: {max_turns: 2}}]\n",
        name="turns",
    )
    run3 = await env.runner().start(env.repo, turns)
    assert "3 turns exceeds max_turns 2" in (env.exec_of(run3, "a")[0].error or "")
    assert env.fake.calls[-1][2].max_turns == 2
