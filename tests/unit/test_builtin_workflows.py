"""The built-in workflows run end to end on the fake engine, with scripted skills."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from compose.core.models import RunStatus
from compose.engines.base import EngineOptions, EngineTask, Usage
from compose.engines.claude.adapter import ALWAYS_ALLOWED, build_options
from compose.engines.fake import Act, Script, edit
from compose.workflows import loader
from tests.unit.runner_helpers import Env

SKILL_FILES = {
    "compose-constitution": ".compose/memory/constitution.md",
    "compose-specify": "spec.md",
    "compose-clarify": "spec.md",
    "compose-plan": "plan.md",
    "compose-tasks": "tasks.md",
    "compose-analyze": None,  # reports only
    "compose-converge": None,  # nothing missing: leaves tasks.md alone
    "compose-implement": "src/feature.py",
}


def skills(task: EngineTask, cwd: Path, options: EngineOptions) -> Script:
    """What each skill writes, in the run's feature folder."""
    feature_dir = f"specs/{options.env['COMPOSE_FEATURE']}"
    target = SKILL_FILES.get(task.text)
    cost = Act(usage=Usage(input_tokens=10, output_tokens=5, cost_usd=0.01, turns=1))
    if target is None:
        return Script([Act(say="No issues found."), cost])
    if not target.startswith((".compose", "src")):
        target = f"{feature_dir}/{target}"
    previous = (cwd / target).read_text() if (cwd / target).exists() else ""
    return Script([*edit(target, f"{previous}{task.text} {task.args or ''}\n"), cost])


@pytest.fixture
def builtin(env: Env) -> Env:
    env.fake.scripts = skills
    return env


def workflow(name: str) -> loader.LoadedWorkflow:
    return loader.resolve(name, None)


def called(env: Env) -> list[str]:
    return [task.text for task, _, _ in env.fake.calls]


async def test_quick(builtin: Env) -> None:
    run = await builtin.runner().start(
        builtin.repo, workflow("quick"), {"spec": "Add a greeting page"}
    )
    assert run.status is RunStatus.COMPLETED, run.error
    assert called(builtin) == [
        "compose-specify",
        "compose-plan",
        "compose-tasks",
        "compose-implement",
        "compose-converge",
    ]
    specify_task = builtin.fake.calls[0][0]
    assert specify_task.args == "Add a greeting page"

    worktree = builtin.worktree(run)
    feature = worktree / "specs" / "001-add-greeting-page"
    assert {p.name for p in feature.iterdir()} == {"spec.md", "plan.md", "tasks.md"}
    for step in ("specify", "plan", "tasks", "implement"):
        (row,) = builtin.exec_of(run, step)
        assert row.files_changed == 1 and row.cost_usd == pytest.approx(0.01), step

    # implement gets no extra tools unless asked
    implement_options = builtin.fake.calls[3][2]
    assert implement_options.engine_options == {"allowed_tools": [""]}
    assert build_options(worktree, implement_options).allowed_tools == ALWAYS_ALLOWED


def converging(gaps: int) -> object:
    """converge appends one open task for its first ``gaps`` rounds; implement checks
    every open task off."""
    rounds: list[int] = []

    def script(task: EngineTask, cwd: Path, options: EngineOptions) -> Script:
        tasks = f"specs/{options.env['COMPOSE_FEATURE']}/tasks.md"
        text = (cwd / tasks).read_text() if (cwd / tasks).exists() else ""
        if task.text == "compose-converge":
            rounds.append(1)
            if len(rounds) > gaps:
                return Script([Act(say="CONVERGED: the code meets the spec, plan and tasks.")])
            line = (
                f"\n## Phase {len(rounds) + 1}: Convergence\n- [ ] T9{len(rounds)} Gap (missing)\n"
            )
            return Script(edit(tasks, text + line))
        if task.text == "compose-implement" and "- [ ]" in text:
            return Script(edit(tasks, text.replace("- [ ]", "- [x]")))
        return skills(task, cwd, options)

    script.rounds = rounds  # type: ignore[attr-defined]
    return script


async def test_quick_converges_remaining_work(builtin: Env) -> None:
    builtin.fake.scripts = converging(gaps=1)  # type: ignore[assignment]
    run = await builtin.runner().start(builtin.repo, workflow("quick"), {"spec": "Add login"})
    assert run.status is RunStatus.COMPLETED, run.error
    assert called(builtin)[3:] == [
        "compose-implement",
        "compose-converge",
        "compose-implement",
        "compose-converge",
    ]
    gaps = builtin.exec_of(run, "implement-gaps")
    assert len(gaps) == 1 and gaps[0].files_changed == 1
    tasks = builtin.worktree(run) / "specs" / "001-add-login" / "tasks.md"
    assert "- [x] T91 Gap (missing)" in tasks.read_text()
    assert [r.output and r.output["exit_code"] for r in builtin.exec_of(run, "open-tasks")] == [
        0,
        1,
    ]


async def test_converge_stops_after_three_rounds(builtin: Env) -> None:
    script = converging(gaps=10)
    builtin.fake.scripts = script  # type: ignore[assignment]
    run = await builtin.runner().start(builtin.repo, workflow("quick"), {"spec": "Add login"})
    assert run.status is RunStatus.COMPLETED, run.error
    assert len(script.rounds) == 3  # type: ignore[attr-defined]
    assert len(builtin.exec_of(run, "implement-gaps")) == 3


async def test_converge_can_be_turned_off(builtin: Env) -> None:
    inputs = {"spec": "Add login", "converge": "false"}
    run = await builtin.runner().start(builtin.repo, workflow("quick"), inputs)
    assert run.status is RunStatus.COMPLETED, run.error
    assert called(builtin)[-1] == "compose-implement"


async def test_quick_allowed_tools(builtin: Env) -> None:
    inputs = {"spec": "Add search", "allowed_tools": "Bash(npm test), Bash(npm run lint)"}
    run = await builtin.runner().start(builtin.repo, workflow("quick"), inputs)
    assert run.status is RunStatus.COMPLETED, run.error
    options = {task.text: opts for task, _, opts in builtin.fake.calls}
    claude = build_options(builtin.worktree(run), options["compose-implement"])
    assert claude.allowed_tools == [*ALWAYS_ALLOWED, "Bash(npm test)", "Bash(npm run lint)"]
    assert build_options(Path("."), options["compose-plan"]).allowed_tools == ALWAYS_ALLOWED


async def test_full_cycle_pauses_at_both_reviews(builtin: Env) -> None:
    runner = builtin.runner()
    run = await runner.start(builtin.repo, workflow("full-cycle"), {"spec": "Export to CSV"})
    assert run.status is RunStatus.PAUSED
    assert run.current_step_id == "review-spec"
    assert called(builtin) == ["compose-constitution", "compose-specify"]  # no clarify
    gate_messages = [e["message"] for e in builtin.events if e["type"] == "gate_waiting"]
    assert gate_messages == ["Review specs/001-export-csv/spec.md before planning."]

    run = await runner.resume(run.id, choice="approve")
    assert run.status is RunStatus.PAUSED and run.current_step_id == "review-plan"
    assert called(builtin)[-1] == "compose-plan"

    run = await runner.resume(run.id, choice="approve")
    assert run.status is RunStatus.COMPLETED, run.error
    assert called(builtin)[2:] == [
        "compose-plan",
        "compose-tasks",
        "compose-analyze",
        "compose-implement",
        "compose-converge",
    ]
    (constitution,) = builtin.exec_of(run, "constitution")
    assert constitution.status.value == "completed"


async def test_full_cycle_with_answers_clarify_and_constitution(
    builtin: Env, run_git: object
) -> None:
    memory = builtin.repo_path / ".compose" / "memory"
    memory.mkdir(parents=True)
    (memory / "constitution.md").write_text("# Principles\n")
    subprocess.run(["git", "add", "."], cwd=builtin.repo_path, check=True)
    subprocess.run(["git", "commit", "-qm", "constitution"], cwd=builtin.repo_path, check=True)

    inputs = {
        "spec": "Dark mode",
        "clarify": "yes",
        "review_spec_verdict": "approve",
        "review_plan_verdict": "approve",
    }
    run = await builtin.runner().start(builtin.repo, workflow("full-cycle"), inputs)
    assert run.status is RunStatus.COMPLETED, run.error
    assert called(builtin) == [
        "compose-specify",
        "compose-clarify",
        "compose-plan",
        "compose-tasks",
        "compose-analyze",
        "compose-implement",
        "compose-converge",
    ]
    assert builtin.exec_of(run, "constitution") == []
    spec = builtin.worktree(run) / "specs" / "001-dark-mode" / "spec.md"
    assert spec.read_text() == "compose-specify Dark mode\ncompose-clarify \n"


async def test_full_cycle_rejected_spec_aborts(builtin: Env) -> None:
    inputs = {"spec": "Risky idea", "review_spec_verdict": "reject"}
    run = await builtin.runner().start(builtin.repo, workflow("full-cycle"), inputs)
    assert run.status is RunStatus.ABORTED
    assert "review-spec" in (run.error or "")
    assert "compose-plan" not in called(builtin)


async def test_pipeline_is_the_default_workflow(builtin: Env) -> None:
    created = builtin.runner().create_run(builtin.repo, None, {"spec": "Add a wishlist"})
    assert created.workflow_id == "pipeline"


async def test_pipeline_pauses_at_clarify_then_runs_to_the_end(builtin: Env) -> None:
    runner = builtin.runner()
    run = await runner.start(builtin.repo, workflow("pipeline"), {"spec": "Export to CSV"})
    assert run.status is RunStatus.PAUSED and run.current_step_id == "clarify-gate"
    assert called(builtin) == ["compose-constitution", "compose-specify", "compose-clarify"]

    run = await runner.resume(run.id, choice="approve")
    assert run.status is RunStatus.COMPLETED, run.error
    assert called(builtin)[3:] == [
        "compose-plan",
        "compose-tasks",
        "compose-analyze",
        "compose-implement",
        "compose-converge",
    ]
    assert builtin.fake.calls[1][0].args == "Export to CSV"
    # no model inputs: every step falls back to the configured default model
    assert {opts.model for _, _, opts in builtin.fake.calls} == {"default-model"}


async def test_pipeline_options_models_and_convergence(builtin: Env) -> None:
    builtin.fake.scripts = converging(gaps=1)  # type: ignore[assignment]
    inputs = {
        "spec": "Add login",
        "skip_clarify": "true",
        "with_checklist": "true",
        "checklist_topic": "security",
        "reasoning": "claude-haiku-5-5",
        "plan": "claude-opus-5-5",
        "code": "claude-sonnet-5-5",
        "allowed_tools": "Bash(npm test)",
    }
    run = await builtin.runner().start(builtin.repo, workflow("pipeline"), inputs)
    assert run.status is RunStatus.COMPLETED, run.error
    calls = [(task.text, task.args, opts.model) for task, _, opts in builtin.fake.calls]
    assert [(text, model) for text, _, model in calls] == [
        ("compose-constitution", "claude-haiku-5-5"),
        ("compose-specify", "claude-haiku-5-5"),
        ("compose-plan", "claude-opus-5-5"),
        ("compose-checklist", "claude-haiku-5-5"),
        ("compose-tasks", "claude-haiku-5-5"),
        ("compose-analyze", "claude-haiku-5-5"),
        ("compose-implement", "claude-sonnet-5-5"),
        ("compose-converge", "claude-haiku-5-5"),
        ("compose-implement", "claude-sonnet-5-5"),
        ("compose-converge", "claude-haiku-5-5"),
    ]
    assert calls[3][1] == "security"
    remaining = builtin.exec_of(run, "implement-remaining")
    assert len(remaining) == 1 and remaining[0].model == "claude-sonnet-5-5"
    claude = build_options(builtin.worktree(run), builtin.fake.calls[-2][2])
    assert claude.allowed_tools == [*ALWAYS_ALLOWED, "Bash(npm test)"]


async def test_pipeline_rejected_clarify_aborts(builtin: Env) -> None:
    inputs = {"spec": "Risky idea", "review_clarify_verdict": "reject"}
    run = await builtin.runner().start(builtin.repo, workflow("pipeline"), inputs)
    assert run.status is RunStatus.ABORTED
    assert "compose-plan" not in called(builtin)


def fixer(passes_on: int | None) -> object:
    attempts: list[str] = []

    def script(task: EngineTask, cwd: Path, options: EngineOptions) -> Script:
        if task.text.startswith("Investigate"):
            feature_dir = f"specs/{options.env['COMPOSE_FEATURE']}"
            return Script(edit(f"{feature_dir}/bug-assessment.md", "root cause\n"))
        if task.text.startswith("Fix the bug"):
            attempts.append(task.text)
            n = len(attempts)
            fixed = passes_on is not None and n >= passes_on
            return Script(edit("attempt.txt", f"{n}\n{'fixed' if fixed else 'broken'}\n"))
        return Script(edit(f"specs/{options.env['COMPOSE_FEATURE']}/bug-fix-summary.md", "s\n"))

    script.attempts = attempts  # type: ignore[attr-defined]
    return script


TEST_COMMAND = (
    "grep -q fixed attempt.txt || { echo FAILED attempt $(head -1 attempt.txt); exit 1; }"
)


async def test_bugfix_loops_until_tests_pass(builtin: Env) -> None:
    script = fixer(passes_on=2)
    builtin.fake.scripts = script  # type: ignore[assignment]
    inputs = {"report": "Crash on empty input", "test_command": TEST_COMMAND}
    run = await builtin.runner().start(builtin.repo, workflow("bugfix"), inputs)
    assert run.status is RunStatus.COMPLETED, run.error

    attempts = script.attempts  # type: ignore[attr-defined]
    assert len(attempts) == 2
    assert "(not run yet)" in attempts[0]
    assert "FAILED attempt 1" in attempts[1]
    tests = builtin.exec_of(run, "test")
    assert [(t.iteration, t.output and t.output["exit_code"]) for t in tests] == [(1, 1), (2, 0)]
    summary_prompt = builtin.fake.calls[-1][0].text
    assert "exit code\n0)" in summary_prompt or "exit code 0" in summary_prompt.replace("\n", " ")


async def test_bugfix_gives_up_after_three_tries(builtin: Env) -> None:
    script = fixer(passes_on=None)
    builtin.fake.scripts = script  # type: ignore[assignment]
    inputs = {"report": "Flaky clock", "test_command": TEST_COMMAND}
    run = await builtin.runner().start(builtin.repo, workflow("bugfix"), inputs)
    assert len(script.attempts) == 3  # type: ignore[attr-defined]
    tests = builtin.exec_of(run, "test")
    assert [t.output and t.output["exit_code"] for t in tests] == [1, 1, 1]
    assert run.status is RunStatus.COMPLETED, run.error
    summary_prompt = builtin.fake.calls[-1][0].text.replace("\n", " ")
    assert "exit code 1" in summary_prompt


SKILLS_MD = """# Suggested skills

- web-design-guidelines (vercel-labs/agent-skills, 120K installs)

## Install

npx skills add vercel-labs/agent-skills@web-design-guidelines
npx skills add anthropics/skills@webapp-testing
npx skills add evil/x; touch pwned
"""


def skill_finder(task: EngineTask, cwd: Path, options: EngineOptions) -> Script:
    if task.text == "compose-find-skills":
        return Script(edit(f"specs/{options.env['COMPOSE_FEATURE']}/skills.md", SKILLS_MD))
    return skills(task, cwd, options)


@pytest.fixture
def fake_npx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An npx on PATH that records its arguments instead of installing anything."""
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    log = tmp_path / "npx.log"
    npx = bin_dir / "npx"
    npx.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n')
    npx.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    return log


PIPELINE_SKILLS = {"spec": "Add a dashboard", "skip_clarify": "true", "with_skills": "true"}


async def test_pipeline_skips_skills_by_default(builtin: Env) -> None:
    inputs = {"spec": "Add a dashboard", "skip_clarify": "true"}
    run = await builtin.runner().start(builtin.repo, workflow("pipeline"), inputs)
    assert run.status is RunStatus.COMPLETED, run.error
    assert "compose-find-skills" not in called(builtin)


async def test_pipeline_finds_skills_after_plan_and_waits(builtin: Env, fake_npx: Path) -> None:
    builtin.fake.scripts = skill_finder  # type: ignore[assignment]
    runner = builtin.runner()
    run = await runner.start(builtin.repo, workflow("pipeline"), PIPELINE_SKILLS)
    assert run.status is RunStatus.PAUSED and run.current_step_id == "skills-gate"
    assert called(builtin)[-2:] == ["compose-plan", "compose-find-skills"]
    find = builtin.fake.calls[-1][0]
    assert "Do not install anything" in (find.args or "")
    assert not fake_npx.exists()

    run = await runner.resume(run.id, choice="install")
    assert run.status is RunStatus.COMPLETED, run.error
    assert called(builtin).index("compose-tasks") > called(builtin).index("compose-find-skills")
    installs = fake_npx.read_text().splitlines()
    assert installs == [
        "--yes skills add vercel-labs/agent-skills@web-design-guidelines -a claude-code -y",
        "--yes skills add anthropics/skills@webapp-testing -a claude-code -y",
    ]  # the malformed line never reaches npx
    assert not (builtin.worktree(run) / "pwned").exists()
    (install,) = builtin.exec_of(run, "skills-install")
    assert install.status.value == "completed"


async def test_pipeline_rejected_skills_are_not_installed(builtin: Env, fake_npx: Path) -> None:
    builtin.fake.scripts = skill_finder  # type: ignore[assignment]
    inputs = {**PIPELINE_SKILLS, "review_skills_verdict": "reject"}
    run = await builtin.runner().start(builtin.repo, workflow("pipeline"), inputs)
    assert run.status is RunStatus.COMPLETED, run.error
    assert builtin.exec_of(run, "skills-install") == []
    assert not fake_npx.exists()
    assert "compose-implement" in called(builtin)
